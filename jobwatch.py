"""Jobwatch: daily aerospace job digest by email.

Sources: Adzuna API, Jooble API, Google Alerts RSS feeds.
Settings live in config.yaml; passwords/keys live in GitHub Secrets.
"""
import hashlib
import html
import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import parse_qs, urlparse

import feedparser
import requests
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(HERE, "seen.json")
SEEN_KEEP_DAYS = 90
WEB_SECTION = "Web & agencies (Google Alerts)"


def log(msg):
    print(msg, flush=True)


def strip_tags(text):
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def kw_regex(words, whole_word=False):
    words = [w.strip().lower() for w in words if w and w.strip()]
    if not words:
        return None
    end = r"\b" if whole_word else ""
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")" + end, re.IGNORECASE)


# ---------------------------------------------------------------- sources
def fetch_adzuna(cfg, region, country):
    app_id, app_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []
    jobs = []
    for page in range(1, int(cfg.get("adzuna_pages", 2)) + 1):
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        params = {
            "app_id": app_id, "app_key": app_key,
            "results_per_page": 50, "what_or": cfg["adzuna_query"],
            "max_days_old": cfg.get("max_days_old", 3), "sort_by": "date",
        }
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            results = r.json().get("results", [])
        except Exception as e:  # keep going if one country fails
            log(f"  Adzuna {country} p{page}: {e}")
            break
        for j in results:
            jobs.append({
                "title": strip_tags(j.get("title")),
                "company": (j.get("company") or {}).get("display_name", ""),
                "location": (j.get("location") or {}).get("display_name", country.upper()),
                "description": strip_tags(j.get("description")),
                "url": j.get("redirect_url", ""),
                "date": (j.get("created") or "")[:10],
                "source": "Adzuna", "region": region,
            })
        if len(results) < 50:
            break
        time.sleep(1.5)
    return jobs


def fetch_jooble(cfg, region, location):
    key = os.getenv("JOOBLE_API_KEY")
    if not key:
        return []
    jobs = []
    for query in cfg.get("jooble_searches", []):
        try:
            r = requests.post(f"https://jooble.org/api/{key}",
                              json={"keywords": query, "location": location, "page": "1"},
                              timeout=30)
            r.raise_for_status()
            results = r.json().get("jobs", [])
        except Exception as e:
            log(f"  Jooble '{query}' in {location}: {e}")
            continue
        for j in results:
            jobs.append({
                "title": strip_tags(j.get("title")),
                "company": j.get("company", ""),
                "location": j.get("location") or location,
                "description": strip_tags(j.get("snippet")),
                "url": j.get("link", ""),
                "date": (j.get("updated") or "")[:10],
                "source": "Jooble" + (f" / {j['source']}" if j.get("source") else ""),
                "region": region,
            })
        time.sleep(1)
    return jobs


def fetch_rss(feed_url):
    jobs = []
    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        log(f"  RSS {feed_url}: {e}")
        return jobs
    for e in feed.entries:
        link = e.get("link", "")
        # Google Alerts wraps links: google.com/url?...&url=REAL_LINK
        real = parse_qs(urlparse(link).query).get("url")
        if real:
            link = real[0]
        jobs.append({
            "title": strip_tags(e.get("title")),
            "company": urlparse(link).netloc.replace("www.", ""),
            "location": "",
            "description": strip_tags(e.get("summary")),
            "url": link,
            "date": (e.get("published") or e.get("updated") or "")[:10],
            "source": "Google Alerts", "region": WEB_SECTION,
        })
    return jobs


# ---------------------------------------------------------------- filtering
def job_id(job):
    norm = lambda s: re.sub(r"\W+", " ", (s or "").lower()).strip()
    key = f"{norm(job['title'])}|{norm(job['company'])}|{norm(job['location'])}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def filter_and_score(jobs, cfg):
    role_re = kw_regex(cfg.get("role_keywords", []))
    avi_re = kw_regex(cfg.get("aviation_keywords", []))
    excl_re = kw_regex(cfg.get("exclude_title_keywords", []), whole_word=True)
    kept = []
    for j in jobs:
        title, text = j["title"], f"{j['title']} {j['description']}"
        if not title or not j["url"]:
            continue
        if excl_re and excl_re.search(title):
            continue
        if j["source"] != "Google Alerts":  # alerts are already targeted searches
            if role_re and not role_re.search(text):
                continue
            if avi_re and not avi_re.search(text):
                continue
        title_roles = {m.lower() for m in role_re.findall(title)} if role_re else set()
        all_roles = {m.lower() for m in role_re.findall(text)} if role_re else set()
        j["score"] = 3 * len(title_roles) + (2 if avi_re and avi_re.search(title) else 0) + len(all_roles)
        j["matched"] = ", ".join(sorted(all_roles))[:120]
        kept.append(j)
    return kept


# ---------------------------------------------------------------- seen store
def load_seen():
    try:
        with open(SEEN_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_seen(seen):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SEEN_KEEP_DAYS)).strftime("%Y-%m-%d")
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f, indent=0, sort_keys=True)


# ---------------------------------------------------------------- email
def build_email(by_region, order, total_found):
    today = datetime.now(timezone.utc).strftime("%d %b %Y")
    n_new = sum(len(v) for v in by_region.values())
    e = html.escape
    parts = [f"""<div style="font-family:Arial,sans-serif;max-width:760px;color:#1f2937">
<h2 style="color:#0b3d91;margin-bottom:4px">✈️ Aerospace job digest – {today}</h2>
<p style="color:#6b7280;margin-top:0">{n_new} new matching jobs (checked {total_found} listings).</p>"""]
    if n_new:
        parts.append("<p>" + " · ".join(
            f'<a href="#{i}" style="color:#0b3d91">{e(r)} ({len(by_region[r])})</a>'
            for i, r in enumerate(order) if by_region.get(r)) + "</p>")
    else:
        parts.append("<p>No new matches today. The search ran normally.</p>")
    for i, region in enumerate(order):
        jobs = by_region.get(region)
        if not jobs:
            continue
        parts.append(f'<h3 id="{i}" style="border-bottom:2px solid #0b3d91;padding-bottom:4px">{e(region)}</h3>')
        for j in jobs:
            meta = " · ".join(e(x) for x in (j["company"], j["location"], j["date"]) if x)
            parts.append(f"""<div style="margin:0 0 14px 0">
<a href="{e(j['url'])}" style="font-weight:bold;color:#0b3d91;font-size:15px">{e(j['title'])}</a><br>
<span style="font-size:13px">{meta}</span><br>
<span style="font-size:12px;color:#6b7280">{e(j['source'])}{' · matched: ' + e(j['matched']) if j.get('matched') else ''}</span>
</div>""")
    parts.append('<p style="font-size:11px;color:#9ca3af">Sent by Jobwatch. Edit config.yaml on GitHub to change searches.</p></div>')
    return f"Aerospace jobs: {n_new} new – {today}", "\n".join(parts)


def send_email(subject, body_html):
    sender = os.environ["EMAIL_ADDRESS"]
    password = os.environ["EMAIL_APP_PASSWORD"]
    to = os.getenv("EMAIL_TO") or sender
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, to
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    with smtplib.SMTP_SSL(host, int(os.getenv("SMTP_PORT", "465"))) as s:
        s.login(sender, password)
        s.sendmail(sender, [a.strip() for a in to.split(",")], msg.as_string())


# ---------------------------------------------------------------- main
def main():
    with open(os.path.join(HERE, "config.yaml")) as f:
        cfg = yaml.safe_load(f)

    if not (os.getenv("ADZUNA_APP_ID") or os.getenv("JOOBLE_API_KEY") or cfg.get("rss_feeds")):
        sys.exit("No sources configured: add Adzuna/Jooble keys as secrets or RSS feeds in config.yaml.")

    all_jobs, order = [], []
    for reg in cfg.get("regions", []):
        name = reg["name"]
        order.append(name)
        for c in reg.get("adzuna", []) or []:
            log(f"Adzuna {c} ...")
            all_jobs += fetch_adzuna(cfg, name, c)
        for loc in reg.get("jooble", []) or []:
            log(f"Jooble {loc} ...")
            all_jobs += fetch_jooble(cfg, name, loc)
    if cfg.get("rss_feeds"):
        order.append(WEB_SECTION)
        for url in cfg["rss_feeds"]:
            log("RSS feed ...")
            all_jobs += fetch_rss(url)

    log(f"Fetched {len(all_jobs)} listings")
    matched = filter_and_score(all_jobs, cfg)

    seen = load_seen()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    by_region, batch_ids = {}, set()
    for j in sorted(matched, key=lambda x: (x["score"], x["date"]), reverse=True):
        jid = job_id(j)
        if jid in seen or jid in batch_ids:
            continue
        batch_ids.add(jid)
        by_region.setdefault(j["region"], []).append(j)

    cap = int(cfg.get("max_jobs_per_region", 40))
    for r in by_region:
        by_region[r] = by_region[r][:cap]
    n_new = sum(len(v) for v in by_region.values())
    log(f"{len(matched)} matched, {n_new} new")

    if n_new or cfg.get("send_when_empty", True):
        subject, body = build_email(by_region, order, len(all_jobs))
        if os.getenv("DRY_RUN"):
            with open(os.path.join(HERE, "preview.html"), "w") as f:
                f.write(body)
            log("DRY_RUN: wrote preview.html instead of emailing")
        else:
            send_email(subject, body)
            log("Email sent")

    # Only remember jobs after the email went out, so nothing is lost on failure
    for v in by_region.values():
        for j in v:
            seen[job_id(j)] = today
    save_seen(seen)


if __name__ == "__main__":
    main()
