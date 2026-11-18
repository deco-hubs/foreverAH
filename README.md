# Forever AH tracker

Hourly auction house prices for materials on **WoW: Forever (EU, Normal ruleset, Horde)**, with price history charts and crafting profit. Runs free on GitHub Actions, so it keeps collecting while your PC is off. You view it as a web page on GitHub Pages.

```
GitHub Actions (every hour) → Blizzard API → data/2026-11.csv (history) → docs/index.html (dashboard)
```

No extra installs: it uses only what comes with Python.

## One-time setup (about 20 minutes)

### 1. Get a Blizzard API key (free)
1. Go to **develop.battle.net**, log in with your Battle.net account, and open **API Access**.
2. Click **Create Client**. Any name works; leave the Redirect URL empty, and tick that it's not a service.
3. Copy the **Client ID** and **Client Secret**. Treat the secret like a password.

### 2. Make a GitHub repository
1. Create a free account on **github.com** if you don't have one.
2. Click **New repository**, name it `forever-ah`, and choose **Public**. GitHub Pages is free only for public repositories. Nothing secret is stored in the files: the key goes in step 3.
3. Put these files in it: either upload them through the web page (**Add file → Upload files**, then drag in everything including the `.github` folder), or let Claude push them for you.

### 3. Add the key as secrets
In the repository: **Settings → Secrets and variables → Actions → New repository secret**. Add two:
- `BNET_CLIENT_ID` = your Client ID
- `BNET_CLIENT_SECRET` = your Client Secret

### 4. Turn on the web page
**Settings → Pages**: under "Build and deployment", choose **Deploy from a branch**, branch **main**, folder **/docs**, then **Save**. Your dashboard will be at `https://<your-username>.github.io/forever-ah/`.

### 5. First runs
1. Open the **Actions** tab. If asked, click to enable workflows.
2. Choose **Update auction prices → Run workflow**, pick **houses**, and run it. Open the finished run and read the table: it lists every auction house with sample prices for Linen Cloth, Copper Ore and Peacebloom. Find the Horde house whose prices match what you see in game, and if it isn't `114`, change `house_id` in `config.toml`.
3. Run the workflow again with **fetch**. From then on it runs by itself every hour.

The charts fill in over the first day. "24 h" and "7-day" figures need a day and a week of data.

## Changing what's tracked
Edit `config.toml` on GitHub (click the file, then the pencil icon):
- **Items:** add a line under `[materials]` with the item's ID, which is the number in its Wowhead URL.
- **Recipes:** add a `[[recipe]]` block. Reagents bought from a vendor take `vendor_price` in copper.

The item IDs and recipes are from the original game and haven't been checked against WoW: Forever. Items never seen on the auction house are listed at the bottom of the dashboard, so a wrong ID shows up there.

## Good to know
- **Blizzard's WoW: Forever API is undocumented.** It works as of November 2026 but could change. If runs start failing, `ah/blizzard.py` is the one file to fix.
- **History is kept as plain CSV**, one file per month in `data/`. You can download and open it in Excel.
- **Scheduled runs can be paused.** GitHub sometimes runs scheduled jobs a few minutes late, and may pause schedules on repositories it thinks are inactive. If you get an email about that, re-enable it in the Actions tab.
- **Running locally:** set `BNET_CLIENT_ID` and `BNET_CLIENT_SECRET` as environment variables, then run `python -m ah fetch`.
