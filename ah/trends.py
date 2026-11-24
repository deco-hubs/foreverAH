"""Trend detection. Recalculated from the CSV history on every run.

How an item counts as "trending":
  1. Daily averages are taken over rolling 24-hour windows ending at the latest snapshot
     (so every "day" contains every hour, and the time-of-day pattern can't fake a trend).
  2. A straight line is fitted through the log of those daily averages. Its slope gives the
     change over the window (7 or 30 days) as a percentage.
  3. R² (0-1) says how steady the move was: near 1 = prices moved consistently in one
     direction; near 0 = random jumps around a flat line.
  4. Items whose price jumps a lot from snapshot to snapshot (usually cheap items with a
     handful of listings) are marked "erratic" and never labelled as trending.
An item is trending up/down when |change| >= min_change, R² >= min_steadiness and not erratic.
Thresholds live in config.toml under [trends].
"""
import math
import statistics as st
from datetime import timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

DEFAULTS = {
    "min_change": 10,        # percent over the window
    "min_steadiness": 0.6,   # R²
    "max_noise": 0.10,       # median absolute snapshot-to-snapshot log change; above = erratic
    "min_days_week": 4,      # daily points needed for a 7-day trend
    "min_days_month": 14,    # daily points needed for a 30-day trend
}


def settings(cfg):
    return {**DEFAULTS, **cfg.get("trends", {})}


MIN_SNAPSHOTS_PER_DAY = 12   # a 24 h window with fewer snapshots is too partial to trust (it may cover only cheap night hours)


def daily_means(rows, now, days):
    """[(days_ago, mean_market, mean_qty)] oldest first, in rolling 24 h windows ending at `now`.
    Windows with fewer than MIN_SNAPSHOTS_PER_DAY snapshots are skipped."""
    buckets = {}
    since = now - timedelta(days=days)
    for t, _, mk, q in rows:
        if t <= since or t > now:
            continue
        k = int((now - t).total_seconds() // 86400)
        if (now - t).total_seconds() % 86400 == 0 and k > 0:
            k -= 1          # a snapshot exactly on a boundary belongs to the newer day
        buckets.setdefault(k, []).append((mk, q))
    return [(k, st.mean(m for m, _ in v), st.mean(q for _, q in v))
            for k, v in sorted(buckets.items(), reverse=True) if len(v) >= MIN_SNAPSHOTS_PER_DAY]


def fit(points):
    """Least-squares line through (x, ln y). Returns (pct change across the x span, R²)."""
    pts = [(x, math.log(y)) for x, y in points if y > 0]
    if len(pts) < 2:
        return None, None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None, None
    slope = sum((x - mx) * (y - my) for x, y in pts) / sxx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (my + slope * (x - mx))) ** 2 for x, y in pts)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0
    span = max(xs) - min(xs)
    return (math.exp(slope * span) - 1) * 100, max(0.0, r2)


def noise(rows, now, days=7):
    recent = [r[2] for r in rows if r[0] > now - timedelta(days=days) and r[2] > 0]
    steps = [abs(math.log(b / a)) for a, b in zip(recent, recent[1:])]
    return st.median(steps) if len(steps) >= 6 else None


def item_trend(rows, now, s):
    out = {"week": None, "week_r2": None, "month": None, "month_r2": None,
           "supply_week": None, "noise": noise(rows, now), "label": None, "daily": []}
    week = daily_means(rows, now, 7)
    month = daily_means(rows, now, 30)
    out["daily"] = month
    if len(week) >= s["min_days_week"]:
        out["week"], out["week_r2"] = fit([(-k, m) for k, m, _ in week])
        out["supply_week"], _ = fit([(-k, q) for k, _, q in week])
    if len(month) >= s["min_days_month"]:
        out["month"], out["month_r2"] = fit([(-k, m) for k, m, _ in month])
    out["erratic"] = out["noise"] is not None and out["noise"] > s["max_noise"]
    if not out["erratic"]:
        # the longer, steady trend wins when there's enough data for it; otherwise the 7-day one
        for chg, r2, span in ((out["month"], out["month_r2"], "30 days"), (out["week"], out["week_r2"], "7 days")):
            if chg is not None and r2 is not None and r2 >= s["min_steadiness"] and abs(chg) >= s["min_change"]:
                out["label"] = ("up" if chg > 0 else "down", chg, span, r2)
                break
    return out


def compute(cfg, hist, now):
    s = settings(cfg)
    return {i["id"]: item_trend(hist[i["id"]], now, s) for i in cfg["items"] if hist.get(i["id"])}


def time_of_day(cfg, hist, now, days=14):
    """Median price index (100 = item's own average) per local hour, over the last `days` days.
    Returns (list of 24 values or None, number of days covered)."""
    tzname = cfg.get("dashboard", {}).get("timezone", "Europe/Oslo")
    tz = ZoneInfo(tzname) if ZoneInfo else None
    since = now - timedelta(days=days)
    s = settings(cfg)
    per_hour = [[] for _ in range(24)]
    first = None
    for rows in hist.values():
        recent = [r for r in rows if r[0] > since and r[2] > 0]
        if len(recent) < 24:
            continue
        n = noise(rows, now)
        if n is not None and n > s["max_noise"]:
            continue    # erratic items would drown the pattern in noise
        avg = st.mean(r[2] for r in recent)
        for t, _, mk, _ in recent:
            local = t.astimezone(tz) if tz else t + timedelta(hours=1)
            per_hour[local.hour].append(mk / avg * 100)
            first = t if first is None or t < first else first
    if first is None or any(len(h) == 0 for h in per_hour):
        return None, 0
    covered = (now - first).total_seconds() / 86400
    med = [st.median(h) for h in per_hour]
    scale = 100 / st.mean(med)          # so the 24 hours average exactly 100
    return [m * scale for m in med], covered


def best_window(index, width=3):
    """Cheapest and dearest `width`-hour windows (start hour, average index)."""
    sums = [(h, st.mean(index[(h + i) % 24] for i in range(width))) for h in range(24)]
    return min(sums, key=lambda x: x[1]), max(sums, key=lambda x: x[1])


def category_index(hist_subset, now, days=30):
    """How a whole category moved: per day, the median of each item's daily average
    divided by that item's own average over the window (100 = normal level).
    Returns [(days_ago, index)] oldest first; erratic items are left out."""
    per_day = {}
    for rows in hist_subset.values():
        n = noise(rows, now)
        if n is not None and n > DEFAULTS["max_noise"]:
            continue
        dm = daily_means(rows, now, days)
        if len(dm) < 2:
            continue
        base = st.mean(m for _, m, _ in dm)
        for k, m, _ in dm:
            per_day.setdefault(k, []).append(m / base * 100)
    series = [(k, st.median(v)) for k, v in sorted(per_day.items(), reverse=True) if len(v) >= 2]
    if not series:
        return series
    scale = 100 / st.mean(v for _, v in series)     # so the line averages 100 over the window
    return [(k, v * scale) for k, v in series]


def supply_series(hist_subset, now, days=30):
    """Total units listed per day across a category: [(days_ago, units)] oldest first."""
    per_day = {}
    for rows in hist_subset.values():
        for k, _, q in daily_means(rows, now, days):
            per_day[k] = per_day.get(k, 0) + q
    return sorted(per_day.items(), reverse=True)


def recipe_profit_history(recipe, hist, now, days=30, ah_cut=0.05):
    """Daily profit per craft, using each day's average prices: [(days_ago, profit_copper)] oldest first.
    Only days where the product and every auction house reagent had a price are included."""
    def by_day(item_id):
        return {k: m for k, m, _ in daily_means(hist.get(item_id, []), now, days)}
    product = by_day(recipe["makes"])
    reagents = [(g, None if g.get("vendor_price") else by_day(g["id"])) for g in recipe["reagents"]]
    out = []
    for k in sorted(product, reverse=True):
        cost, ok = 0, True
        for g, series in reagents:
            price = g["vendor_price"] if series is None else series.get(k)
            if price is None:
                ok = False
                break
            cost += price * g["qty"]
        if ok:
            out.append((k, product[k] * recipe.get("makes_qty", 1) * (1 - ah_cut) - cost))
    return out
