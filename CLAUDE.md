# CLAUDE.md: context for Claude working on this project

## What this is
A WoW: Forever auction house price tracker for one Horde auction house: EU, ruleset 2 (Normal). It runs on GitHub Actions every 20 minutes (Blizzard publishes about hourly; duplicate snapshots are skipped, and the page is rebuilt every run), uses Python 3.11+ stdlib only, stores history as CSV in `data/`, and writes a static dashboard to `docs/index.html` for GitHub Pages. It's a sibling of the user's investment tracker and follows the same style.

## Blizzard API (undocumented for Forever, as of Nov 2026)
- **Auth:** client credentials at https://oauth.battle.net/token, with secrets `BNET_CLIENT_ID` and `BNET_CLIENT_SECRET`.
- **Namespace:** `dynamic-forever-eu`. Rulesets replace realms: 1 PvP, 2 Normal, 3 RP, 15 RP-PvP.
- **Endpoints:**
  - `/data/wow/ruleset/{r}/auctions/` lists houses. The trailing slash is required.
  - `/data/wow/ruleset/{r}/auctions/{house}` returns auctions, with `buyout` per auction.
  - `/data/wow/ruleset/{r}/auctions/{house}/commodities` returns commodities, with `unit_price`.
- **Quirk:** the ruleset in the path reportedly doesn't filter results; the house id decides.
- **EU Horde house ids:** 113, 114, 115, 120 and 124. The user's house is **114** (Normal, Horde), confirmed on 2026-11-18 by matching in-game prices.
- **Item IDs:** vanilla IDs work: all 72 tracked items were found on the first live run (2026-11-18). Many items 404 on `/data/wow/item/{id}` in `static-forever`.

## Code map
- `ah/blizzard.py`: HTTP client.
- `ah/stats.py`: listings to min / market (mean of the cheapest 15% of units) / qty, plus gold formatting.
- `ah/history.py`: CSV history, plus `state.json` for skipping duplicate snapshots by Last-Modified.
- `ah/site.py`: dashboard table with price changes over 24 h / 7 d / 1 m / 3 m / 6 m (vs that day's average) and a 7-day sparkline. Each item has a chart drawn in the browser from embedded data, with ranges 7 days / 1 / 3 / 6 months / Max (4-hour points up to a month, daily beyond). The `[dashboard] featured` category ("Fishing") is shown first. The crafting-profit section sits right after the featured section and is hidden when config has no `[[recipe]]`. Recipes take an optional `note`. The user removed the bolt and smelting recipes on 2026-11-18 and added Mithril Spurs and Mithril Shield Spike on 2026-11-24. The user buys ore and smelts the bars (1 ore per bar). One row per item makes the grinding stones from bought Solid Stone (4 each); the other buys Solid Grinding Stones ready-made, for comparison.
- `ah/trends.py`: trend engine. Daily averages in rolling 24 h windows, a log-linear fit over 7 and 30 days (change %, R² as steadiness), a noise filter that marks erratic items, supply trend, and a time-of-day price pattern in local time. Thresholds are under `[trends]` in config.toml; the timezone is `[dashboard] timezone`.
- The dashboard has one tab per category plus Crafting and Trends, in the order of `[dashboard] tab_order` (Crafting, Ores and bars, Fishing, Pearls, Herbs, then the rest, then Trends). Each category tab has summary tiles (items, typical 7-day change, rising/falling, units listed and supply trend, biggest mover, most erratic), a category price-level chart and a units-listed chart (30 days), the category's best time to buy, and the item table. The Crafting tab has the profit table with 7-day average profit and a 30-day profit chart per recipe, plus a table of every material and product the recipes use. The Trends tab shows the best time to buy and sell, rising and falling items, the featured category at a glance, category medians and the Hall of L33t. Trending items get ▲/▼ badges in the price tables. Tabs are linked by URL hash (#fishing, #crafting, #trends).
- Daily averages skip 24 h windows with fewer than 12 snapshots (`trends.MIN_SNAPSHOTS_PER_DAY`), so a partial first day can't skew trends.
- `ah/theme.py`: original artwork as inline SVG: the night-market header banner and line icons per section. The look is a single dark "night market" theme with gold accents and serif headings, and prices are shown with gold/silver/copper coin icons (`stats.coins`). Don't use Blizzard's art (sprites, icons, logos, race designs); keep the graphics original.
- `ah/__main__.py`: CLI commands `fetch`, `houses` and `report`. `report` loads 400 days of history.

## Easter egg
- A price of exactly 1337 copper (13s 37c) is special: the coin display shimmers (`stats.LEET`, class `money leet`), a "L33T PRICE SPOTTED" banner shows when the latest snapshot has one, and the Trends tab lists every sighting in a "Hall of L33t". The user asked for this; keep it.

## User's interests
- Fishing reagents (Stonescale Eel, Firefin Snapper and the like) matter most. The user doesn't care about bolts or smelting.

## Conventions
- Read-only: never call anything that posts or buys.
- Keep stdlib only, and keep everything in `config.toml` editable on GitHub's web editor.
- Never commit secrets.

## Ideas not built yet
- Deal alerts: market well below its 7-day average, e.g. a GitHub issue or a push notification (trend data from `ah/trends.py` could drive this).
- Item names from the API where available.
- Compare factions (Alliance and Blackwater houses).
- Daily roll-up of old hourly rows if `data/` gets large: about 90 KB/day at 92 items, so roughly 33 MB a year.
