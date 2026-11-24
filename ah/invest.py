"""Investment watchlist: items you might buy now and sell later.

What you write in config.toml (by hand, on GitHub's web editor):
  [[catalyst]]    a dated event that should change demand, e.g. raids opening.
  [[investment]]  an item to watch, why (thesis), what it's used for later, which
                  catalyst it waits for, and optionally how many you bought and at what price.

What this module works out on every run, from the price history:
  - where today's price sits in the range seen since tracking began (0% = cheapest, 100% = dearest)
  - today's price vs. the 7-day average
  - the 7-day trend and the supply trend (from ah/trends.py)
  - days until the catalyst
  - a signal: Buy zone / Accumulate / Pricey, wait / Sell window / Hold / Not listed yet
  - your profit or loss, if you filled in bought_qty and bought_at

It only reads prices. It never buys or sells anything.
"""
import re
import statistics as st
from datetime import datetime, timedelta, timezone

from . import trends

AH_CUT = 0.05

# signal rules (see signal() below)
BUY_POSITION = 33        # price in the cheapest third of its tracked range ...
BUY_VS_WEEK = -5         # ... or at least 5% under its 7-day average
PRICEY_POSITION = 80     # in the top fifth of its range ...
PRICEY_VS_WEEK = 10      # ... or 10% over its 7-day average
SELL_DAYS_AFTER = 21     # a sell window lasts this long after the catalyst ...
SELL_GAIN = 15           # ... if the price is at least 15% over its pre-catalyst average


def parse_money(v):
    """'12s 50c', '8g', '1g 2s 3c', or a whole number of copper -> copper (int). None if empty."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v)
    total, found = 0, False
    for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([gsc])", str(v).lower()):
        total += float(amount) * {"g": 10000, "s": 100, "c": 1}[unit]
        found = True
    if not found:
        raise SystemExit(f"config.toml: can't read the price {v!r}. Write it like \"12s 50c\" or \"8g 20s\".")
    return int(round(total))


def catalysts(cfg, now):
    """[{name, date (datetime UTC), note, days}] sorted by date. days < 0 = already happened."""
    out = []
    for c in cfg.get("catalyst", []):
        d = c["date"]
        when = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) if not isinstance(d, str) \
            else datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
        out.append({"name": c["name"], "date": when, "note": c.get("note", ""),
                    "days": (when - now).total_seconds() / 86400})
    return sorted(out, key=lambda c: c["date"])


def _signal(e):
    if e["now"] is None:
        return "unlisted", "Not listed yet"
    cat = e["catalyst"]
    pos, vs = e["position"], e["vs_week"]
    if cat and cat["days"] < 0:
        if -cat["days"] <= SELL_DAYS_AFTER and e["vs_before"] is not None and e["vs_before"] >= SELL_GAIN:
            return "sell", "Sell window"
        if -cat["days"] <= SELL_DAYS_AFTER:
            return "hold", "Hold, no spike yet"
        return "hold", "Catalyst passed"
    cheap = (pos is not None and pos <= BUY_POSITION) or (vs is not None and vs <= BUY_VS_WEEK)
    dear = (pos is not None and pos >= PRICEY_POSITION) or (vs is not None and vs >= PRICEY_VS_WEEK)
    if cheap and not dear:
        return "buy", "Buy zone"
    if dear and not cheap:
        return "pricey", "Pricey, wait for a dip"
    return "accumulate", "Accumulate slowly"


def evaluate(cfg, hist, tr, now):
    """One dict per [[investment]], in config order."""
    items = {i["id"]: i for i in cfg["items"]}
    cats = {c["name"]: c for c in catalysts(cfg, now)}
    out = []
    for inv in cfg.get("investment", []):
        iid = inv["id"]
        it = items.get(iid)
        e = {"id": iid, "name": it["name"] if it else f"item {iid}", "inv": inv, "missing": it is None,
             "catalyst": cats.get(inv.get("catalyst")), "now": None, "position": None, "low": None, "high": None,
             "vs_week": None, "vs_before": None, "trend": None, "supply": None, "daily": [], "qty_now": None,
             "bought_qty": inv.get("bought_qty"), "bought_at": parse_money(inv.get("bought_at")),
             "value": None, "pnl": None, "pnl_pct": None}
        rows = hist.get(iid, [])
        if rows:
            last = rows[-1]
            if last[0] == now:
                e["now"], e["qty_now"] = last[2], last[3]
            daily = trends.daily_means(rows, now, 400)
            # range: daily averages once there are a few days, otherwise individual snapshots
            pool = [m for _, m, _ in daily] if len(daily) >= 3 else [r[2] for r in rows]
            e["low"], e["high"] = min(pool), max(pool)
            if e["now"] is not None and e["high"] > e["low"]:
                e["position"] = max(0, min(100, (e["now"] - e["low"]) / (e["high"] - e["low"]) * 100))
            week = [r[2] for r in rows if r[0] > now - timedelta(days=7)]
            if e["now"] is not None and len(week) >= 12:
                e["vs_week"] = (e["now"] / st.mean(week) - 1) * 100
            cat = e["catalyst"]
            if cat and cat["days"] < 0 and e["now"] is not None:
                before = [r[2] for r in rows if cat["date"] - timedelta(days=7) <= r[0] < cat["date"]]
                if before:
                    e["vs_before"] = (e["now"] / st.mean(before) - 1) * 100
            t = tr.get(iid)
            if t:
                e["trend"], e["supply"], e["daily"] = t["week"], t["supply_week"], t["daily"]
        if e["bought_qty"] and e["bought_at"] and e["now"] is not None:
            cost = e["bought_qty"] * e["bought_at"]
            e["value"] = e["bought_qty"] * e["now"] * (1 - AH_CUT)
            e["pnl"] = e["value"] - cost
            e["pnl_pct"] = e["pnl"] / cost * 100
        e["signal"], e["signal_text"] = _signal(e)
        out.append(e)
    return out
