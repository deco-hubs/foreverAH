"""Command line.

  python -m ah fetch     download the latest snapshot, add it to the history, rebuild the dashboard
  python -m ah houses    list every auction house with its size and a sample price (to find yours)
  python -m ah report    rebuild the dashboard from the saved history only (no download)
"""
import argparse
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from . import config, history, site, stats
from .blizzard import Client

SAMPLE_ITEMS = {2589: "Linen Cloth", 2770: "Copper Ore", 2447: "Peacebloom"}


def fetch(cfg):
    ah = cfg["auction_house"]
    client = Client(*config.secrets(), region=ah["region"], locale=ah.get("locale", "en_GB"))
    auctions, commodities, last_modified = client.house(ah["ruleset"], ah["house_id"])
    state = history.load_state()
    if last_modified and state.get("last_modified") == last_modified:
        print(f"No new snapshot since {last_modified}; nothing to do.")
        return False

    snap_time = (parsedate_to_datetime(last_modified) if last_modified
                 else datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    listings = stats.unit_listings(auctions, commodities)
    tracked = {i["id"] for i in cfg["items"]}
    summaries = {iid: stats.summarize(lst) for iid, lst in listings.items() if iid in tracked}
    path = history.append(snap_time.isoformat().replace("+00:00", "Z"), summaries)
    history.save_state({"last_modified": last_modified, "time_utc": snap_time.isoformat(),
                        "listings": len(auctions) + len(commodities), "tracked_found": len(summaries)})
    print(f"Snapshot {snap_time:%Y-%m-%d %H:%M} UTC: {len(auctions)} auctions + {len(commodities)} commodity "
          f"listings; {len(summaries)}/{len(tracked)} tracked items on sale -> {path.name}")
    return True


def report(cfg):
    hist = history.load(days=400)   # enough for 6-month changes and a year of chart
    if not hist:
        print("No history yet: run 'fetch' first.")
        return
    latest = max(rows[-1][0] for rows in hist.values())
    out = site.build(cfg, hist, latest, config.DOCS / "index.html")
    print(f"Dashboard: {out}")


def houses(cfg):
    ah = cfg["auction_house"]
    client = Client(*config.secrets(), region=ah["region"], locale=ah.get("locale", "en_GB"))
    index = client.house_index(ah["ruleset"])
    print(f"{len(index)} auction houses in {ah['region'].upper()} ruleset {ah['ruleset']}.")
    print("Compare the sample prices with what you see in game to find yours.\n")
    print(f"{'id':>4}  {'name':<28} {'listings':>9}  " + "  ".join(f"{n:>14}" for n in SAMPLE_ITEMS.values()))
    for h in sorted(index, key=lambda h: h["id"]):
        try:
            a, c, _ = client.house(ah["ruleset"], h["id"])
        except Exception as e:
            print(f"{h['id']:>4}  {h.get('name', '?'):<28} error: {e}")
            continue
        lst = stats.unit_listings(a, c)
        samples = [stats.gold(stats.summarize(lst[i])["min"]) if lst.get(i) else "–" for i in SAMPLE_ITEMS]
        print(f"{h['id']:>4}  {h.get('name', '?'):<28} {len(a) + len(c):>9}  " +
              "  ".join(f"{s:>14}" for s in samples))


def main():
    ap = argparse.ArgumentParser(prog="ah")
    ap.add_argument("command", choices=["fetch", "houses", "report"], nargs="?", default="fetch")
    args = ap.parse_args()
    cfg = config.load()
    if args.command == "houses":
        houses(cfg)
    elif args.command == "fetch":
        if fetch(cfg):
            report(cfg)
    else:
        report(cfg)


if __name__ == "__main__":
    sys.exit(main())
