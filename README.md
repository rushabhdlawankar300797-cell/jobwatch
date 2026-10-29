# ✈️ Jobwatch – daily aerospace job digest

Every morning this tool searches job sites across Europe, Australia, Singapore, Canada, the Middle East, Southeast Asia and India. It looks for CAMO, technical records, technical documentation, technical services, procurement, supply chain, logistics and consulting roles in aviation. It then emails you **only the jobs you haven't seen before**, grouped by region in your priority order.

It runs free on GitHub's servers, so your computer doesn't need to be on. No coding needed: everything below happens in a web browser. Setup takes about 30 minutes.

**What it searches**
- **Adzuna**: France, Germany, Netherlands, Belgium, Austria, Italy, Spain, Poland, UK, Switzerland, Australia, Singapore, Canada, India
- **Jooble**: Ireland, Portugal, Czech Republic, Sweden, Denmark, Romania, UAE, Saudi Arabia, Qatar, Oman, Bahrain, Kuwait, Indonesia, Philippines, Vietnam, Thailand. Jooble collects listings from many job boards and agency sites.
- **Google Alerts** (optional): the general web, recruitment agencies and company career pages

---

## Step 1 – Get a free Adzuna key (5 min)
1. Go to **https://developer.adzuna.com** and click **Register**.
2. After you log in, open your dashboard and find your **Application ID** and **Application Key**.
3. Copy both into a notepad for now.

## Step 2 – Get a free Jooble key (5 min)
1. Go to **https://jooble.org/api/about** and fill in the form to request an API key.
2. The key arrives by email, sometimes after a day or so. You can finish the other steps and add the key later; the tool will skip Jooble until the key is in place.

## Step 3 – Create a Gmail "app password" (5 min)
The tool sends the email from your Gmail account. It needs a special password that you can revoke at any time; this is not your normal password.
1. Go to **https://myaccount.google.com/security** and make sure **2-Step Verification** is turned ON.
2. Go to **https://myaccount.google.com/apppasswords**, type the name `jobwatch`, and click **Create**.
3. Copy the 16-character password it shows you.

(If you don't use Gmail, see "Other email providers" at the bottom.)

## Step 4 – Put the files on GitHub (10 min)
1. Create a free account at **https://github.com**.
2. Click **+** (top right) → **New repository**. Name it `jobwatch`, choose **Private**, then click **Create repository**.
3. On the new page, click **uploading an existing file**. Drag in these files: `jobwatch.py`, `config.yaml`, `requirements.txt`, `seen.json`, `README.md`. Then click **Commit changes**.
4. The schedule file sits in a hidden folder, so add it separately:
   **Add file → Create new file**. In the name box type exactly `.github/workflows/daily.yml` (typing the `/` creates the folders). Paste in the contents of `daily.yml`, then click **Commit changes**.

## Step 5 – Add your keys as "secrets" (5 min)
In your repository, go to **Settings → Secrets and variables → Actions → New repository secret**. Add each of these, one at a time:

| Name | Value |
|---|---|
| `ADZUNA_APP_ID` | Application ID from step 1 |
| `ADZUNA_APP_KEY` | Application Key from step 1 |
| `JOOBLE_API_KEY` | key from step 2 (add it when it arrives) |
| `EMAIL_ADDRESS` | your Gmail address |
| `EMAIL_APP_PASSWORD` | 16-character password from step 3 |
| `EMAIL_TO` | *(optional)* a different address to receive the digest; separate several addresses with commas |

Secrets are encrypted. Nobody, including you, can read them back after you save them.

## Step 6 (optional, recommended) – Google Alerts for the wider web
This adds the general web, recruitment agencies and company sites to your digest.
1. Go to **https://www.google.com/alerts**.
2. Type a search, for example:
   - `"CAMO" aviation vacancy`
   - `"technical records" aircraft job`
   - `"continuing airworthiness" recruitment`
   - `aviation procurement job`
   - `aerospace supply chain vacancy`
3. Click **Show options**, set **Deliver to → RSS feed**, then click **Create Alert**.
4. On the alerts page, click the **RSS icon** next to the alert and copy the link from your browser's address bar.
5. Open `config.yaml` on GitHub, click the ✏️ pencil icon, and add the link under `rss_feeds:`. It should look like this:
   ```yaml
   rss_feeds:
     - "https://www.google.com/alerts/feeds/1234567890/9876543210"
     - "https://www.google.com/alerts/feeds/1234567890/1111111111"
   ```
   Click **Commit changes**.

## Step 7 – Test it
Go to the **Actions** tab → **Daily job digest** → **Run workflow**. After 1–3 minutes the email should arrive. A green tick means the run worked. A red ✗ means something failed: click the run to see the error, and GitHub will also email you about it.

The **first email is the biggest**, because every current listing counts as new. After that, you'll only get jobs that appeared since the previous day.

---

## LinkedIn
LinkedIn doesn't allow automated searching, and accounts that scrape it get restricted. Use LinkedIn's own alerts instead:
1. On LinkedIn Jobs, search for something like `CAMO`, set the location (e.g. *European Union*), and switch on **Set alert**.
2. Under alert settings, choose **Daily** and **Email**.
3. Repeat for each role and region you want (for example "technical records", "aviation procurement", "aviation supply chain").

Those alert emails arrive in the same inbox as your digest. In Gmail you can create a filter that gives them and the digest a shared label such as "Job search".

## Changing what it searches
Open `config.yaml` on GitHub and click ✏️. You can:
- **Add or remove countries** in `regions`, and reorder regions to change their priority in the email.
- **Add job keywords** to `role_keywords` (e.g. `quality`, `compliance`, `engineering support`).
- **Block unwanted titles** with `exclude_title_keywords`.
- **Stop "nothing new today" emails** by setting `send_when_empty: false`.

Click **Commit changes**. The next run uses your new settings.

**Change the send time:** edit `.github/workflows/daily.yml` and change `"0 6 * * *"` (06:00 UTC). For example, `"30 4 * * *"` means 04:30 UTC.

## Troubleshooting
- **No email arrives:** check your spam folder. Check that `EMAIL_ADDRESS` and `EMAIL_APP_PASSWORD` are correct, and that the app password has no spaces.
- **"Authentication failed":** create a new Gmail app password and update the secret.
- **Too many irrelevant jobs:** remove broad words from `role_keywords` (e.g. `records`, `material`, `planning`, `contract`), or add words to `exclude_title_keywords`.
- **Too few jobs:** add more countries or keywords, or raise `adzuna_pages` to 3.
- **Jooble errors about limits:** remove a few entries from `jooble_searches` or from the Jooble countries.

## Other email providers
Gmail is recommended. Many other providers (including Outlook.com) no longer allow simple password sending from scripts. If your provider supports SSL sending on port 465 with an app password, add two more secrets, `SMTP_HOST` and `SMTP_PORT`. Then add matching `SMTP_HOST: ${{ secrets.SMTP_HOST }}` and `SMTP_PORT: ${{ secrets.SMTP_PORT }}` lines under `env:` in `daily.yml`.
