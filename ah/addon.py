"""Price file for the ForeverNetWorth in-game addon.

WoW addons can't go online, so on every new snapshot the tracker writes the market value of
every stackable (commodity) item on the auction house, plus the tracked items, into a Lua file:

    docs/addon/ForeverNetWorth/Prices.lua

GitHub Pages serves it, and the small sync script on the PC (tools/sync_forever_addon.py)
copies the addon files plus this price file into the game's AddOns folder. The game reads it at
login or /reload. manifest.json lists the files so the sync script knows what to download.

To keep the repo small it's rewritten at most every EVERY_HOURS hours (prices for net worth
don't need to be minute-fresh), and gear (non-commodity auctions) is left out: soulbound gear
can't be sold anyway and counts at vendor price in the addon.
"""
from datetime import datetime
import json
from pathlib import Path

from . import stats

ADDON = "ForeverNetWorth"
FILES = ["ForeverNetWorth.toc", "Core.lua", "UI.lua", "Prices.lua"]
EVERY_HOURS = 6


def write_prices(listings, snap_time, cfg, docs_dir, commodity_ids=None, force=False):
    """Returns the number of items written, or 0 if the file is still fresh enough."""
    folder = Path(docs_dir) / "addon" / ADDON
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder.parent / "manifest.json"
    if not force and manifest.exists():
        try:
            last = datetime.fromisoformat(json.loads(manifest.read_text(encoding="utf-8"))["prices_updated"])
            if (snap_time - last).total_seconds() < EVERY_HOURS * 3600 - 300:
                return 0
        except (ValueError, KeyError):
            pass
    keep = set(commodity_ids) if commodity_ids is not None else set(listings)
    keep |= {i["id"] for i in cfg["items"]}
    ah = cfg["auction_house"]
    lines = [
        "-- Written by the Forever AH tracker on every new auction house snapshot. Don't edit: it's replaced.",
        "-- items[itemID] = market value in copper (average of the cheapest 15% of units listed).",
        "local _, ns = ...",
        "ns.prices = {",
        f"  updated = {int(snap_time.timestamp())},",
        f'  region = "{ah["region"]}", house = {int(ah["house_id"])},',
        "  items = {",
    ]
    n = 0
    for iid in sorted(i for i in listings if i in keep):
        s = stats.summarize(listings[iid])
        lines.append(f"[{int(iid)}]={int(s['market'])},")
        n += 1
    lines += ["  },", "}", ""]
    (folder / "Prices.lua").write_text("\n".join(lines), encoding="utf-8")
    manifest.write_text(json.dumps(
        {"addon": ADDON, "files": FILES, "prices_updated": snap_time.isoformat(), "items": n}, indent=1), encoding="utf-8")
    return n
