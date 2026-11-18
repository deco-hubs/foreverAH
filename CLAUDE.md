# CLAUDE.md: context for Claude working on this project

## What this is
A WoW: Forever auction house price tracker for one Horde auction house: EU, ruleset 2 (Normal). It runs hourly on GitHub Actions, uses Python 3.11+ stdlib only, stores history as CSV in `data/`, and writes a static dashboard to `docs/index.html` for GitHub Pages. It's a sibling of the user's investment tracker and follows the same style.

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
- `ah/site.py`: dashboard with tables, sparklines, a 30-day chart per item and crafting profit (5% AH cut).
- `ah/__main__.py`: CLI commands `fetch`, `houses` and `report`.

## Conventions
- Read-only: never call anything that posts or buys.
- Keep stdlib only, and keep everything in `config.toml` editable on GitHub's web editor.
- Never commit secrets.

## Ideas not built yet
- Deal alerts: market well below its 7-day average, e.g. a GitHub issue or a push notification.
- Item names from the API where available.
- Compare factions (Alliance and Blackwater houses).
- Daily roll-up of old hourly rows if `data/` gets large (~60 KB/day at ~70 items).
