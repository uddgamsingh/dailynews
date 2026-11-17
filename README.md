# DailyBrief

A static news site (AI, International, National) that updates itself every day.

- `index.html` – the website (reads `data/news.json`)
- `scripts/fetch_news.py` – fetches free RSS feeds + Hacker News Algolia API (Python stdlib only, no API keys)
- `.github/workflows/daily-news.yml` – GitHub Action that runs the script daily at 00:30 UTC and commits `data/news.json`
- `data/news.json` – generated data

## Deploy on GitHub (5 steps)

1. Create a new GitHub repository and upload all these files (keep the folder structure, including the hidden `.github` and `.nojekyll`).
2. **Settings → Actions → General → Workflow permissions** → choose **Read and write permissions** → Save.
3. **Settings → Pages** → Source: **Deploy from a branch** → Branch: `main`, folder `/ (root)` → Save.
4. **Actions** tab → **Update daily news** → **Run workflow** (first run, so the site has data).
5. Open `https://<your-username>.github.io/<repo-name>/`

After that it refreshes automatically every day. To change the time, edit the `cron` line in the workflow (times are UTC). To add outlets or countries, edit the feed lists at the top of `scripts/fetch_news.py`.

## Test locally

    python scripts/fetch_news.py
    python -m http.server 8000     # then open http://localhost:8000

Note: GitHub pauses scheduled workflows after 60 days of no repository activity; the daily commits normally keep it active.
