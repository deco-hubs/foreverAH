"""Builds docs/index.html: one self-contained page, served by GitHub Pages."""
import html
import json
from datetime import timedelta

from . import trends
from .stats import LEET, coins, gold
from .theme import BANNER, heading

AH_CUT = 0.05


# ---------- small helpers ----------------------------------------------------

def _pct(new, old):
    if not new or not old:
        return None
    return (new / old - 1) * 100


def _pct_html(v, need=None):
    if v is None:
        tip = f' title="Needs {need} of history"' if need else ""
        return f'<span class="muted"{tip}>–</span>'
    cls = "up" if v > 0.5 else "down" if v < -0.5 else "muted"
    return f'<span class="{cls}">{v:+.0f}%</span>'


def _at_or_before(rows, when):
    best = None
    for r in rows:
        if r[0] <= when:
            best = r
        else:
            break
    return best


def _daily_avg_at(daily, when):
    """Average market on the day containing `when`; None if history doesn't reach back that far."""
    if not daily or daily[0][0] > when + timedelta(hours=12):
        return None
    best = None
    for t, _, mk in daily:
        if t <= when:
            best = mk
        else:
            break
    return best


def _bucket(rows, hours):
    """Average market (and min) per time bucket, to keep charts light."""
    out, cur, acc = [], None, []
    for t, mn, mk, _ in rows:
        key = int(t.timestamp() // (hours * 3600))
        if key != cur and acc:
            out.append((acc[0][0], sum(a[1] for a in acc) / len(acc), sum(a[2] for a in acc) / len(acc)))
            acc = []
        cur = key
        acc.append((t, mn, mk))
    if acc:
        out.append((acc[0][0], sum(a[1] for a in acc) / len(acc), sum(a[2] for a in acc) / len(acc)))
    return out


def _sparkline(points, w=120, h=28):
    if len(points) < 2:
        return '<span class="muted small">collecting…</span>'
    ts = [p[0].timestamp() for p in points]
    vs = [p[2] for p in points]
    lo, hi = min(vs), max(vs)
    span_t, span_v = (ts[-1] - ts[0]) or 1, (hi - lo) or 1
    xy = " ".join(f"{(t - ts[0]) / span_t * (w - 4) + 2:.1f},{h - 3 - (v - lo) / span_v * (h - 6):.1f}"
                  for t, v in zip(ts, vs))
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">'
            f'<polyline points="{xy}" fill="none" stroke="var(--accent)" stroke-width="1.5"/></svg>')


# ---------- page -------------------------------------------------------------


# ---------- trends tab -------------------------------------------------------

def _steadiness(r2):
    if r2 is None:
        return "–"
    return "very steady" if r2 >= 0.85 else "steady" if r2 >= 0.6 else "bumpy" if r2 >= 0.3 else "no clear direction"


def _daily_spark(daily, w=110, h=26):
    vals = [m for _, m, _ in daily]
    if len(vals) < 2:
        return '<span class="muted small">collecting…</span>'
    lo, hi = min(vals), max(vals)
    xy = " ".join(f"{i / (len(vals) - 1) * (w - 4) + 2:.1f},{h - 3 - (v - lo) / ((hi - lo) or 1) * (h - 6):.1f}"
                  for i, v in enumerate(vals))
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">'
            f'<polyline points="{xy}" fill="none" stroke="var(--accent)" stroke-width="1.5"/></svg>')


def _hour_chart(index, cheap, dear, w=720, h=190, L=44, B=26, T=12, R=8):
    lo, hi = min(index) - 1.5, max(index) + 1.5
    Y = lambda v: T + (1 - (v - lo) / ((hi - lo) or 1)) * (h - T - B)
    bw = (w - L - R) / 24
    cheap_h = {(cheap[0] + i) % 24 for i in range(3)}
    dear_h = {(dear[0] + i) % 24 for i in range(3)}
    bars = []
    for hr, v in enumerate(index):
        x = L + hr * bw
        y0, y1 = sorted((Y(v), Y(100)))
        colour = "var(--up)" if hr in cheap_h else "var(--down)" if hr in dear_h else "var(--accent)"
        bars.append(f'<rect x="{x + 2:.1f}" y="{y0:.1f}" width="{bw - 4:.1f}" height="{max(y1 - y0, 1):.1f}" '
                    f'fill="{colour}" opacity="0.85"><title>{hr:02d}:00 – {v:.0f}</title></rect>')
        if hr % 3 == 0:
            bars.append(f'<text x="{x + bw / 2:.1f}" y="{h - 8}" text-anchor="middle" class="axis">{hr:02d}</text>')
    ticks = "".join(f'<text x="{L - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" class="axis">{v:.0f}</text>'
                    for v in (lo + 1.5, 100, hi - 1.5))
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Price level by hour of day">'
            f'<line x1="{L}" x2="{w - R}" y1="{Y(100):.1f}" y2="{Y(100):.1f}" stroke="var(--muted)" stroke-dasharray="3 3"/>'
            f'{"".join(bars)}{ticks}</svg>')


def _trends_tab(cfg, hist, now, tr, items_by_id, featured):
    s = trends.settings(cfg)
    tzname = cfg.get("dashboard", {}).get("timezone", "Europe/Oslo")
    out = [f"""<p class="small muted">Recalculated every run from the price history. An item is <b>trending</b> when a line fitted
through its daily average prices moves at least {s['min_change']:.0f}% over 7 or 30 days <i>and</i> the move is steady
(R² ≥ {s['min_steadiness']}), not one spike. Items whose price jumps around from hour to hour are left out as erratic.
Thresholds are under <code>[trends]</code> in config.toml.</p>"""]

    # 1. time of day
    index, covered = trends.time_of_day(cfg, hist, now)
    out.append(heading("Best time to buy and sell", "clock"))
    if index is None or covered < 1:
        out.append('<p class="muted">Needs at least a day of history.</p>')
    else:
        cheap, dear = trends.best_window(index)
        out.append(f"""<p>Prices are lowest around <b class="up">{cheap[0]:02d}:00–{(cheap[0] + 3) % 24:02d}:00</b>
({cheap[1] - 100:+.0f}% vs. the daily average) and highest around <b class="down">{dear[0]:02d}:00–{(dear[0] + 3) % 24:02d}:00</b>
({dear[1] - 100:+.0f}%). Buy in the green hours; list your own goods before the red ones.</p>
{_hour_chart(index, cheap, dear)}
<p class="small muted">Median price level by hour ({tzname.split('/')[-1]} time), 100 = each item's average, last {min(covered, 14):.0f} days, erratic items excluded.</p>""")

    # 2. movers
    def mover_rows(direction):
        rows = [(k, v) for k, v in tr.items() if v["label"] and v["label"][0] == direction]
        rows.sort(key=lambda kv: -abs(kv[1]["label"][1]))
        if not rows:
            return f'<p class="muted">Nothing is trending {direction} right now.</p>'
        body = []
        for iid, v in rows:
            it = items_by_id[iid]
            _, chg, span, r2 = v["label"]
            sup = v["supply_week"]
            body.append(f"""<tr><td><a href="https://www.wowhead.com/forever/item={iid}" target="_blank" rel="noopener">{html.escape(it['name'])}</a>
<div class="small muted">{html.escape(it.get('category', ''))}</div></td>
<td class="num"><b class="{'up' if chg > 0 else 'down'}">{chg:+.0f}%</b><div class="small muted">{span}</div></td>
<td>{_steadiness(r2)}</td>
<td class="num">{f"{sup:+.0f}%" if sup is not None else "–"}</td>
<td class="num">{coins(hist[iid][-1][2])}</td>
<td class="spark-cell">{_daily_spark(v['daily'])}</td></tr>""")
        return ("""<table class="trend"><thead><tr><th>Item</th><th class="num">Change</th><th>How steady</th>
<th class="num">Supply, 7 d</th><th class="num">Price now</th><th>Last 30 days</th></tr></thead><tbody>"""
                + "".join(body) + "</tbody></table>")

    out.append(heading("Trending up", "up", extra=' <span class="muted small">getting more expensive</span>') + mover_rows("up"))
    out.append(heading("Trending down", "down", extra=' <span class="muted small">getting cheaper</span>') + mover_rows("down"))

    # 3. featured category at a glance
    if featured:
        fr = []
        for it in (i for i in cfg["items"] if i.get("category") == featured and i["id"] in tr):
            v = tr[it["id"]]
            if v["erratic"]:
                state = '<span class="muted">erratic, too jumpy to call</span>'
            elif v["label"]:
                state = f'<b class="{"up" if v["label"][0] == "up" else "down"}">trending {v["label"][0]}</b>'
            elif v["week"] is None:
                state = '<span class="muted">collecting data</span>'
            else:
                state = '<span class="muted">no clear trend</span>'
            wk = f'{v["week"]:+.0f}%' if v["week"] is not None else "–"
            fr.append(f"""<tr><td>{html.escape(it['name'])}</td><td class="num">{wk}</td><td>{_steadiness(v['week_r2'])}</td>
<td>{state}</td><td class="spark-cell">{_daily_spark(v['daily'])}</td></tr>""")
        out.append(f"""{heading(html.escape(featured) + " at a glance", category=featured)}
<table class="trend"><thead><tr><th>Item</th><th class="num">7-day trend</th><th>How steady</th><th>Status</th><th>Last 30 days</th></tr></thead>
<tbody>{"".join(fr)}</tbody></table>""")

    # 4. categories
    cats = {}
    for it in cfg["items"]:
        v = tr.get(it["id"])
        if v and v["week"] is not None and not v["erratic"]:
            c = cats.setdefault(it.get("category", "Other"), {"chg": [], "up": 0, "down": 0})
            c["chg"].append(v["week"])
            if v["label"]:
                c[v["label"][0]] += 1
    if cats:
        import statistics as st
        crow = "".join(
            f"""<tr><td>{html.escape(c)}</td><td class="num">{_pct_html(st.median(d['chg']))}</td>
<td class="num">{d['up'] or '–'}</td><td class="num">{d['down'] or '–'}</td><td class="num">{len(d['chg'])}</td></tr>"""
            for c, d in sorted(cats.items(), key=lambda cd: -st.median(cd[1]["chg"])))
        out.append(f"""{heading("By category", "grid")}
<table class="trend"><thead><tr><th>Category</th><th class="num">Typical 7-day change</th><th class="num">Trending up</th>
<th class="num">Trending down</th><th class="num">Items</th></tr></thead><tbody>{crow}</tbody></table>""")

    erratic = [items_by_id[k]["name"] for k, v in tr.items() if v["erratic"]]
    if erratic:
        out.append(f'<p class="small muted" style="margin-top:24px">Left out as erratic (price jumps too much between snapshots, usually '
                   f'because only a few cheap listings exist): {html.escape(", ".join(sorted(erratic)))}.</p>')
    return "\n".join(out)


def build(cfg, hist, latest_time, out_path):
    ah = cfg["auction_house"]
    names = {i["id"]: i["name"] for i in cfg["items"]}
    now = latest_time
    current, rows_html, never_seen, chart_data = {}, {}, [], {}
    tr = trends.compute(cfg, hist, now)
    items_by_id = {i["id"]: i for i in cfg["items"]}

    for item in cfg["items"]:
        iid, rows = item["id"], hist.get(item["id"], [])
        if not rows:
            never_seen.append(item)
            continue
        last = rows[-1]
        listed_now = last[0] == now
        if listed_now:
            current[iid] = last[2]
        day_ago = _at_or_before(rows, now - timedelta(hours=24))
        week = [r for r in rows if r[0] >= now - timedelta(days=7)]
        avg7 = sum(r[2] for r in week) / len(week) if week else None
        daily = _bucket(rows, 24)
        changes = [_pct(last[2], day_ago[2]) if day_ago else None]
        for days in (7, 30, 91, 182):
            then = _daily_avg_at(daily, now - timedelta(days=days))
            changes.append(_pct(last[2], then) if then else None)
        chart_data[iid] = {
            "h": [[int(t.timestamp() // 3600), round(mn), round(mk)]
                  for t, mn, mk in _bucket([r for r in rows if r[0] >= now - timedelta(days=31)], 4)],
            "d": [[int(t.timestamp() // 3600), round(mn), round(mk)] for t, mn, mk in daily],
        }
        name = html.escape(item["name"])
        status = "" if listed_now else ' <span class="tag">not listed now</span>'
        lab = tr.get(iid, {}).get("label")
        if lab:
            arrow = "▲" if lab[0] == "up" else "▼"
            status += (f' <span class="badge {lab[0]}" title="Trending {lab[0]}: {lab[1]:+.0f}% over {lab[2]}, '
                       f'{_steadiness(lab[3])}">{arrow} {abs(lab[1]):.0f}%</span>')
        change_cells = "".join(f'<td class="num">{_pct_html(c, need)}</td>'
                               for c, need in zip(changes, ("1 day", "7 days", "1 month", "3 months", "6 months")))
        rows_html.setdefault(item.get("category", "Other"), []).append(f"""
<tr class="item" data-id="{iid}" tabindex="0" title="Click for the price chart">
  <td><a href="https://www.wowhead.com/forever/item={iid}" target="_blank" rel="noopener">{name}</a>{status}</td>
  <td class="num"><b>{coins(last[2])}</b><div class="small muted">min {coins(last[1])}</div></td>
  <td class="num">{last[3]:,}</td>
  <td class="num">{coins(avg7)}</td>
  {change_cells}
  <td class="spark-cell">{_sparkline(_bucket(week, 2))}</td>
</tr>
<tr class="detail" id="d{iid}" hidden><td colspan="11"><div class="ranges" role="group" aria-label="Chart range">
<button data-r="7">7 days</button><button data-r="30" class="on">1 month</button><button data-r="91">3 months</button><button data-r="182">6 months</button><button data-r="0">Max</button></div>
<div class="chartbox" data-id="{iid}"></div>
<p class="small muted"><span class="key solid"></span> market value &nbsp; <span class="key dashed"></span> cheapest listing &nbsp;<span class="res"></span></p></td></tr>""")

    # crafting profit
    craft = []
    for r in cfg["recipe"]:
        cost, missing = 0, []
        for g in r["reagents"]:
            price = g.get("vendor_price") or current.get(g["id"])
            if price is None:
                missing.append(names.get(g["id"], str(g["id"])))
            else:
                cost += price * g["qty"]
        sell = current.get(r["makes"])
        if sell is None:
            missing.append(names.get(r["makes"], str(r["makes"])))
        if missing:
            craft.append((None, r, cost, None, missing))
            continue
        revenue = sell * r.get("makes_qty", 1) * (1 - AH_CUT)
        craft.append((revenue - cost, r, cost, revenue, []))
    craft.sort(key=lambda c: (c[0] is None, -(c[0] or 0)))
    craft_rows = []
    for profit, r, cost, revenue, missing in craft:
        if missing:
            craft_rows.append(f'<tr><td>{html.escape(r["name"])}</td><td colspan="4" class="muted">'
                              f'no current price for {html.escape(", ".join(missing))}</td></tr>')
            continue
        margin = profit / cost * 100 if cost else None
        verdict = "Craft and sell" if profit > 0 else "Sell the materials"
        note = f'<div class="small muted">{html.escape(r["note"])}</div>' if r.get("note") else ""
        craft_rows.append(f"""<tr><td>{html.escape(r["name"])}<div class="small"><b class="{'up' if profit > 0 else 'down'}">{verdict}</b></div>{note}</td>
  <td class="num">{coins(cost)}</td><td class="num">{coins(revenue)}</td>
  <td class="num"><b class="{'up' if profit > 0 else 'down'}">{coins(profit)}</b></td>
  <td class="num">{_pct_html(margin)}</td></tr>""")

    featured = cfg.get("dashboard", {}).get("featured")
    order = ([featured] if featured in rows_html else []) + [c for c in rows_html if c != featured]
    craft_html = "" if not craft_rows else f"""{heading("Crafting profit", "hammer")}
<p class="small muted">Sale value is after the 5% auction house cut. Recipes and reagents are set in config.toml.</p>
<table class="craft"><thead><tr><th>Recipe</th><th class="num">Materials cost</th><th class="num">Sells for</th><th class="num">Profit per craft</th><th class="num">Margin</th></tr></thead>
<tbody>{"".join(craft_rows)}</tbody></table>"""
    section = lambda cat: f"""{heading(html.escape(cat), category=cat)}
<table class="items"><thead><tr><th>Item</th><th class="num">Market value</th><th class="num">Listed</th><th class="num">7-day avg</th>
<th class="num">24 h</th><th class="num">7 d</th><th class="num">1 m</th><th class="num">3 m</th><th class="num">6 m</th><th>Last 7 days</th></tr></thead>
<tbody>{"".join(rows_html[cat])}</tbody></table>"""
    lead = section(order[0]) if order and order[0] == featured else ""
    sections = lead + craft_html + "".join(section(c) for c in order if not (lead and c == featured))

    flagged = ""
    if never_seen:
        flagged = (heading("Never seen on this auction house", "question") + "<p class='muted'>Either nobody has listed these yet, or the "
                   "item ID is wrong for WoW: Forever. Check the ID on Wowhead and fix it in config.toml.</p><ul>" +
                   "".join(f"<li>{html.escape(i['name'])} <span class='muted'>(id {i['id']})</span></li>"
                           for i in never_seen) + "</ul>")

    # 13s 37c easter egg: current sightings (toast) and all-time sightings (Hall of L33t)
    leet_now, leet_ever = [], []
    for it in cfg["items"]:
        for t, mn, mk, _ in hist.get(it["id"], []):
            if LEET in (mn, mk):
                leet_ever.append((t, it["name"], "market value" if mk == LEET else "cheapest listing"))
                if t == now:
                    leet_now.append(it["name"])
    leet_toast = "" if not leet_now else f"""<div class="leet-toast" role="status"><span class="sparks" aria-hidden="true">✦ ✧ ✦</span>
<b>L33T PRICE SPOTTED</b> {html.escape(", ".join(leet_now))} is at exactly {coins(LEET)} right now <span class="sparks" aria-hidden="true">✦ ✧ ✦</span></div>"""
    trends_html = _trends_tab(cfg, hist, now, tr, items_by_id, featured)
    if leet_ever:
        leet_ever.sort(reverse=True)
        trends_html += (heading("Hall of L33t", "gem", extra=' <span class="muted small">every time a price hit exactly 13s 37c</span>')
                        + '<table class="trend"><thead><tr><th>When (UTC)</th><th>Item</th><th>Which price</th></tr></thead><tbody>'
                        + "".join(f"<tr><td>{t:%d %b %Y %H:%M}</td><td>{html.escape(n)}</td><td>{w}</td></tr>" for t, n, w in leet_ever[:50])
                        + "</tbody></table>")
    n_trending = sum(1 for v in tr.values() if v["label"])
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forever AH · {html.escape(ah['region'].upper())} Horde</title>
<style>
/* "night market" theme: one dark palette, gold accents */
:root {{ --bg:#10141b; --panel:#171d27; --fg:#efe6d2; --muted:#9a9384; --line:#29313e; --accent:#e2b048; --up:#86d39a; --down:#f2917a; --hover:#1f2733;
  --serif: "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  background-image: radial-gradient(1200px 400px at 50% -100px, #1c2536 0%, transparent 70%); }}
main {{ max-width:1000px; margin:0 auto; padding:0 20px 64px; }}
.hero {{ position:relative; margin:0 -20px; border-radius:0 0 18px 18px; overflow:hidden; border-bottom:1px solid #3a3222; }}
.banner {{ display:block; width:100%; height:200px; }}
.hero-text {{ position:absolute; left:28px; bottom:18px; right:28px; text-shadow:0 2px 8px #000; }}
h1 {{ font-family:var(--serif); font-size:34px; font-weight:700; margin:0; letter-spacing:.02em; color:#f6e6b4; font-variant:small-caps; }}
.hero .sub {{ color:#d8cfbb; }}
@media (max-width:640px) {{ .banner {{ height:150px; }} h1 {{ font-size:25px; }} .hero-text {{ left:18px; bottom:12px; }} .hero .sub {{ font-size:12px; }} }}
h2 {{ font-family:var(--serif); font-size:20px; font-weight:700; margin:40px 0 12px; color:#f1dfae; display:flex; align-items:center; gap:10px; letter-spacing:.01em; }}
h2 .icon {{ color:var(--accent); flex:none; width:26px; height:26px; padding:4px; border:1px solid #4a3f28; border-radius:50%; background:#1c1a14; box-sizing:content-box; }}
h2 .muted {{ font-family:system-ui, sans-serif; font-weight:400; font-size:13px; }}
table {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; border-collapse:separate; border-spacing:0; overflow:hidden; }}
tr:last-child > td {{ border-bottom:none; }}
thead th {{ background:#1b222d; }}
.money {{ white-space:nowrap; }}
.coin {{ display:inline-block; width:.72em; height:.72em; border-radius:50%; margin:0 .28em 0 .12em; vertical-align:-.04em; box-shadow:inset 0 -1px 0 rgba(0,0,0,.35); }}
.money.leet {{ padding:1px 6px; border-radius:6px; background:linear-gradient(90deg,#3b2a0c,#6a4b12,#3b2a0c); background-size:200% 100%;
  box-shadow:0 0 10px #e2b04888; color:#fff3c4; }}
.leet-toast {{ margin:18px 0 0; padding:12px 16px; border:1px solid var(--accent); border-radius:12px; background:#231d10;
  font-family:var(--serif); font-size:17px; text-align:center; box-shadow:0 0 24px #e2b04855; }}
.leet-toast b {{ color:#ffe08a; letter-spacing:.08em; margin-right:6px; }}
.sparks {{ color:var(--accent); display:inline-block; margin:0 8px; }}
@media (prefers-reduced-motion: no-preference) {{
  .money.leet {{ animation:shimmer 2.2s linear infinite; }}
  .leet-toast {{ animation:pop .6s cubic-bezier(.2,1.6,.4,1) both; }}
  .sparks {{ animation:twinkle 1.4s ease-in-out infinite; }}
}}
@keyframes shimmer {{ to {{ background-position:-200% 0; }} }}
@keyframes pop {{ from {{ transform:scale(.6); opacity:0; }} to {{ transform:scale(1); opacity:1; }} }}
@keyframes twinkle {{ 50% {{ opacity:.25; transform:scale(.8) rotate(20deg); }} }}
.coin.gold {{ background:radial-gradient(circle at 35% 30%, #fff3b8, #e2b048 55%, #9c6d16); }}
.coin.silver {{ background:radial-gradient(circle at 35% 30%, #ffffff, #c2c8d2 55%, #7d8592); }}
.coin.copper {{ background:radial-gradient(circle at 35% 30%, #ffd1a8, #c27a45 55%, #7c4422); }}
.sub {{ color:var(--muted); margin:6px 0 0; font-size:14px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th, td {{ padding:8px 8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:middle; }}
th {{ font-size:12px; font-weight:600; color:var(--muted); }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
tr.item {{ cursor:pointer; }} tr.item:hover, tr.item:focus {{ background:var(--hover); outline:none; }}
tr.detail td {{ background:var(--hover); padding:12px 16px; }}
a {{ color:inherit; text-decoration-color:var(--line); }} a:hover {{ text-decoration-color:var(--accent); }}
.muted {{ color:var(--muted); }} .small {{ font-size:12px; }}
.up {{ color:var(--up); }} .down {{ color:var(--down); }}
.tabs {{ display:flex; gap:4px; margin:22px 0 6px; border-bottom:1px solid var(--line); font-family:var(--serif); font-size:17px; }}
.tabs a {{ padding:8px 14px; text-decoration:none; color:var(--muted); border-bottom:2px solid transparent; margin-bottom:-1px; }}
.tabs a.on {{ color:var(--fg); border-bottom-color:var(--accent); font-weight:600; }}
.tabs .count {{ font-size:11px; background:var(--accent); color:var(--bg); border-radius:9px; padding:1px 6px; margin-left:4px; }}
.badge {{ font-size:11px; font-weight:600; border-radius:4px; padding:0 5px; margin-left:6px; white-space:nowrap; }}
.badge.up {{ color:var(--up); border:1px solid var(--up); }} .badge.down {{ color:var(--down); border:1px solid var(--down); }}
code {{ font-size:12px; }}
@media (max-width:640px) {{ .trend th:nth-child(3), .trend td:nth-child(3), .trend th:nth-child(4), .trend td:nth-child(4) {{ display:none; }} }}
.tag {{ font-size:11px; color:var(--muted); border:1px solid var(--line); border-radius:4px; padding:0 5px; margin-left:6px; }}
.chart {{ width:100%; height:auto; }} .grid {{ stroke:var(--line); }} .axis {{ fill:var(--muted); font-size:11px; }}
.key {{ display:inline-block; width:18px; vertical-align:middle; border-top:2px solid var(--accent); }}
.key.dashed {{ border-top:1px dashed var(--muted); }}
.ranges {{ display:flex; gap:6px; margin-bottom:8px; }}
.ranges button {{ font:inherit; font-size:12px; padding:3px 10px; border:1px solid var(--line); border-radius:6px; background:transparent; color:var(--muted); cursor:pointer; }}
.ranges button.on {{ color:var(--fg); border-color:var(--accent); background:#2a2416; }}
.items th:nth-child(n+5):nth-child(-n+9) {{ width:52px; }}
@media (max-width:900px) {{ .items th:nth-child(4), .items td:nth-child(4), .spark-cell, .items th:last-child, .trend th:last-child {{ display:none; }} }}
@media (max-width:640px) {{ .craft th:nth-child(5), .craft td:nth-child(5) {{ display:none; }} }}
@media (max-width:640px) {{ .items th:nth-child(3), .items td:nth-child(3), .items th:nth-child(8), .items td:nth-child(8), .items th:nth-child(9), .items td:nth-child(9) {{ display:none; }} }}
</style></head><body><main>
<header class="hero">{BANNER}<div class="hero-text"><h1>Forever Auction House</h1>
<p class="sub">{html.escape(ah['region'].upper())} · ruleset {ah['ruleset']} · Horde (house {ah['house_id']}) · snapshot <time data-utc="{now.isoformat()}">{now.strftime('%d %b %Y %H:%M')} UTC</time></p></div></header>
{leet_toast}
<nav class="tabs" role="tablist"><a href="#prices" role="tab" data-tab="prices">Prices</a><a href="#trends" role="tab" data-tab="trends">Trends{f' <span class="count">{n_trending}</span>' if n_trending else ''}</a></nav>
<section id="tab-prices">
<p class="small muted">Market value = average price of the cheapest 15% of units listed. ▲/▼ = trending (see the Trends tab). 24 h compares with the snapshot a day ago; 7 d to 6 m compare with that day's average price. "–" means not enough history yet. Click any row for its chart.</p>
{sections}
{flagged}
</section>
<section id="tab-trends" hidden>
{trends_html}
</section>
<p class="small muted" style="margin-top:40px">Data: Blizzard Battle.net API (undocumented WoW: Forever endpoints), checked every 20 minutes by GitHub Actions. Item names link to Wowhead's WoW: Forever database.</p>
</main>
<script>
const HIST = {json.dumps(chart_data, separators=(",", ":"))};
const gold = c => {{ c = Math.round(c); const g = Math.floor(c / 10000), s = Math.floor(c / 100) % 100, k = c % 100;
  if (g >= 100) return g.toLocaleString('nb-NO') + 'g'; if (g) return s ? g + 'g ' + s + 's' : g + 'g';
  if (s) return k ? s + 's ' + k + 'c' : s + 's'; return k + 'c'; }};
function draw(box, range) {{
  const data = HIST[box.dataset.id], res = box.parentNode.querySelector('.res');
  const src = range && range <= 30 ? data.h : data.d, cut = range ? (src.at(-1)[0] - range * 24) : -Infinity;
  const pts = src.filter(p => p[0] >= cut);
  res.textContent = '· ' + (src === data.h ? '4-hour' : 'daily') + ' averages';
  if (pts.length < 2) {{ box.innerHTML = '<p class="muted">Not enough history for this range yet.</p>'; return; }}
  const W = 720, H = 220, L = 78, B = 26, T = 14, R = 12;
  const vals = pts.flatMap(p => [p[1], p[2]]); let lo = Math.min(...vals) * 0.95, hi = Math.max(...vals) * 1.05;
  const t0 = pts[0][0], t1 = pts.at(-1)[0], X = t => L + (t - t0) / ((t1 - t0) || 1) * (W - L - R), Y = v => T + (1 - (v - lo) / ((hi - lo) || 1)) * (H - T - B);
  const line = i => pts.map(p => X(p[0]).toFixed(1) + ',' + Y(p[i]).toFixed(1)).join(' ');
  const fmt = h => new Date(h * 3600e3).toLocaleDateString([], {{ day: 'numeric', month: 'short' }});
  let grid = '';
  for (const f of [0.1, 0.5, 0.9]) {{ const v = lo + (hi - lo) * f; grid += `<line x1="${{L}}" x2="${{W - R}}" y1="${{Y(v).toFixed(1)}}" y2="${{Y(v).toFixed(1)}}" class="grid"/><text x="${{L - 8}}" y="${{(Y(v) + 4).toFixed(1)}}" text-anchor="end" class="axis">${{gold(v)}}</text>`; }}
  box.innerHTML = `<svg class="chart" viewBox="0 0 ${{W}} ${{H}}" role="img" aria-label="Price history">${{grid}}
<polyline points="${{line(1)}}" fill="none" stroke="var(--muted)" stroke-width="1" stroke-dasharray="3 3"/>
<polyline points="${{line(2)}}" fill="none" stroke="var(--accent)" stroke-width="2"/>
<text x="${{L}}" y="${{H - 6}}" class="axis">${{fmt(t0)}}</text><text x="${{W - R}}" y="${{H - 6}}" text-anchor="end" class="axis">${{fmt(t1)}}</text></svg>`;
}}
document.querySelectorAll('tr.detail').forEach(d => {{
  d.querySelectorAll('.ranges button').forEach(b => b.addEventListener('click', () => {{
    d.querySelectorAll('.ranges button').forEach(x => x.classList.toggle('on', x === b));
    draw(d.querySelector('.chartbox'), Number(b.dataset.r));
  }}));
}});
document.querySelectorAll('tr.item').forEach(r => {{
  const toggle = e => {{ if (e.target.closest('a')) return; const d = document.getElementById('d' + r.dataset.id); d.hidden = !d.hidden;
    if (!d.hidden && !d.querySelector('svg')) draw(d.querySelector('.chartbox'), Number(d.querySelector('.ranges .on').dataset.r)); }};
  r.addEventListener('click', toggle);
  r.addEventListener('keydown', e => {{ if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); toggle(e); }} }});
}});
function showTab() {{
  const name = location.hash === '#trends' ? 'trends' : 'prices';
  document.getElementById('tab-prices').hidden = name !== 'prices';
  document.getElementById('tab-trends').hidden = name !== 'trends';
  document.querySelectorAll('.tabs a').forEach(a => a.classList.toggle('on', a.dataset.tab === name));
}}
window.addEventListener('hashchange', showTab); showTab();
document.querySelectorAll('time[data-utc]').forEach(t => {{
  t.textContent = new Date(t.dataset.utc).toLocaleString([], {{ day:'numeric', month:'short', hour:'2-digit', minute:'2-digit' }});
}});
</script>
</body></html>"""
    out_path.write_text(page, encoding="utf-8")
    (out_path.parent / "latest.json").write_text(json.dumps(
        {"time_utc": now.isoformat(), "house": ah["house_id"],
         "market": {names.get(k, str(k)): v for k, v in current.items()}}, indent=1) + "\n")
    return out_path
