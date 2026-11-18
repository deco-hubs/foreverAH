"""Builds docs/index.html: one self-contained page, served by GitHub Pages."""
import html
import json
from datetime import timedelta

from .stats import gold

AH_CUT = 0.05


# ---------- small helpers ----------------------------------------------------

def _pct(new, old):
    if not new or not old:
        return None
    return (new / old - 1) * 100


def _pct_html(v):
    if v is None:
        return '<span class="muted">–</span>'
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


def _chart(points, name, w=720, h=220, pad_l=78, pad_b=26, pad_t=14):
    if len(points) < 2:
        return '<p class="muted">The chart appears after a few hours of data.</p>'
    ts = [p[0].timestamp() for p in points]
    mins, mks = [p[1] for p in points], [p[2] for p in points]
    lo, hi = min(mins + mks), max(mins + mks)
    lo, hi = lo * 0.95, hi * 1.05
    span_t, span_v = (ts[-1] - ts[0]) or 1, (hi - lo) or 1
    X = lambda t: pad_l + (t - ts[0]) / span_t * (w - pad_l - 12)
    Y = lambda v: pad_t + (1 - (v - lo) / span_v) * (h - pad_t - pad_b)
    line = lambda vals: " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in zip(ts, vals))
    grid = "".join(
        f'<line x1="{pad_l}" x2="{w - 12}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="grid"/>'
        f'<text x="{pad_l - 8}" y="{Y(v) + 4:.1f}" text-anchor="end" class="axis">{gold(v)}</text>'
        for v in (lo + span_v * f for f in (0.1, 0.5, 0.9)))
    d0, d1 = points[0][0].strftime("%d %b"), points[-1][0].strftime("%d %b")
    return f"""<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(name)} price history">
{grid}
<polyline points="{line(mins)}" fill="none" stroke="var(--muted)" stroke-width="1" stroke-dasharray="3 3"/>
<polyline points="{line(mks)}" fill="none" stroke="var(--accent)" stroke-width="2"/>
<text x="{pad_l}" y="{h - 6}" class="axis">{d0}</text>
<text x="{w - 12}" y="{h - 6}" text-anchor="end" class="axis">{d1}</text>
</svg>
<p class="small muted"><span class="key solid"></span> market value &nbsp; <span class="key dashed"></span> cheapest listing &nbsp;· 4-hour averages, last 30 days</p>"""


# ---------- page -------------------------------------------------------------

def build(cfg, hist, latest_time, out_path):
    ah = cfg["auction_house"]
    names = {i["id"]: i["name"] for i in cfg["items"]}
    now = latest_time
    current, rows_html, never_seen = {}, {}, []

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
        spark = _bucket(week, 2)
        detail = _bucket([r for r in rows if r[0] >= now - timedelta(days=30)], 4)
        name = html.escape(item["name"])
        status = "" if listed_now else ' <span class="tag">not listed now</span>'
        rows_html.setdefault(item.get("category", "Other"), []).append(f"""
<tr class="item" data-id="{iid}" tabindex="0" title="Click for the 30-day chart">
  <td><a href="https://www.wowhead.com/forever/item={iid}" target="_blank" rel="noopener">{name}</a>{status}</td>
  <td class="num"><b>{gold(last[2])}</b><div class="small muted">min {gold(last[1])}</div></td>
  <td class="num">{last[3]:,}</td>
  <td class="num">{_pct_html(_pct(last[2], day_ago[2]) if day_ago else None)}</td>
  <td class="num">{gold(avg7)}</td>
  <td class="num">{_pct_html(_pct(last[2], avg7))}</td>
  <td>{_sparkline(spark)}</td>
</tr>
<tr class="detail" id="d{iid}" hidden><td colspan="7">{_chart(detail, item["name"])}</td></tr>""")

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
        craft_rows.append(f"""<tr><td>{html.escape(r["name"])}<div class="small muted">{verdict}</div></td>
  <td class="num">{gold(cost)}</td><td class="num">{gold(revenue)}</td>
  <td class="num"><b class="{'up' if profit > 0 else 'down'}">{gold(profit)}</b></td>
  <td class="num">{_pct_html(margin)}</td></tr>""")

    featured = cfg.get("dashboard", {}).get("featured")
    order = ([featured] if featured in rows_html else []) + [c for c in rows_html if c != featured]
    craft_html = "" if not craft_rows else f"""<h2>Crafting profit</h2>
<p class="small muted">Sale value is after the 5% auction house cut. Recipes and reagents are set in config.toml.</p>
<table><thead><tr><th>Recipe</th><th class="num">Materials cost</th><th class="num">Sells for</th><th class="num">Profit per craft</th><th class="num">Margin</th></tr></thead>
<tbody>{"".join(craft_rows)}</tbody></table>"""
    sections = "".join(
        f"""<h2>{html.escape(cat)}</h2>
<table><thead><tr><th>Item</th><th class="num">Market value</th><th class="num">Listed</th>
<th class="num">24 h</th><th class="num">7-day avg</th><th class="num">vs 7-day</th><th>Last 7 days</th></tr></thead>
<tbody>{"".join(rows_html[cat])}</tbody></table>""" for cat in order)

    flagged = ""
    if never_seen:
        flagged = ("<h2>Never seen on this auction house</h2><p class='muted'>Either nobody has listed these yet, or the "
                   "item ID is wrong for WoW: Forever. Check the ID on Wowhead and fix it in config.toml.</p><ul>" +
                   "".join(f"<li>{html.escape(i['name'])} <span class='muted'>(id {i['id']})</span></li>"
                           for i in never_seen) + "</ul>")

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forever AH · {html.escape(ah['region'].upper())} Horde</title>
<style>
:root {{ --bg:#fbfaf7; --fg:#1d1c1a; --muted:#77736b; --line:#e6e2d9; --accent:#a8741a; --up:#2f7a4f; --down:#b3412e; --hover:#f3efe6; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#15140f; --fg:#ecE8dc; --muted:#9b968a; --line:#2c2a24; --accent:#e0ad4f; --up:#6cc394; --down:#ec8a74; --hover:#1f1d17; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width:1000px; margin:0 auto; padding:36px 20px 64px; }}
h1 {{ font-size:24px; margin:0; letter-spacing:-.01em; }}
h2 {{ font-size:16px; margin:40px 0 10px; }}
.sub {{ color:var(--muted); margin:4px 0 0; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th, td {{ padding:8px 8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:middle; }}
th {{ font-size:12px; font-weight:600; color:var(--muted); }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
tr.item {{ cursor:pointer; }} tr.item:hover, tr.item:focus {{ background:var(--hover); outline:none; }}
tr.detail td {{ background:var(--hover); padding:12px 16px; }}
a {{ color:inherit; text-decoration-color:var(--line); }} a:hover {{ text-decoration-color:var(--accent); }}
.muted {{ color:var(--muted); }} .small {{ font-size:12px; }}
.up {{ color:var(--up); }} .down {{ color:var(--down); }}
.tag {{ font-size:11px; color:var(--muted); border:1px solid var(--line); border-radius:4px; padding:0 5px; margin-left:6px; }}
.chart {{ width:100%; height:auto; }} .grid {{ stroke:var(--line); }} .axis {{ fill:var(--muted); font-size:11px; }}
.key {{ display:inline-block; width:18px; vertical-align:middle; border-top:2px solid var(--accent); }}
.key.dashed {{ border-top:1px dashed var(--muted); }}
@media (max-width:700px) {{ th:nth-child(5), td:nth-child(5), th:nth-child(7), td:nth-child(7) {{ display:none; }} }}
</style></head><body><main>
<h1>Forever auction house</h1>
<p class="sub">{html.escape(ah['region'].upper())} · ruleset {ah['ruleset']} · Horde (house {ah['house_id']}) · snapshot <time data-utc="{now.isoformat()}">{now.strftime('%d %b %Y %H:%M')} UTC</time></p>
<p class="small muted">Market value = average price of the cheapest 15% of units listed. Click any row for its 30-day chart.</p>
{craft_html}
{sections}
{flagged}
<p class="small muted" style="margin-top:40px">Data: Blizzard Battle.net API (undocumented WoW: Forever endpoints), updated hourly by GitHub Actions. Item names link to Wowhead's WoW: Forever database.</p>
</main>
<script>
document.querySelectorAll('tr.item').forEach(r => {{
  const toggle = e => {{ if (e.target.closest('a')) return; const d = document.getElementById('d' + r.dataset.id); d.hidden = !d.hidden; }};
  r.addEventListener('click', toggle);
  r.addEventListener('keydown', e => {{ if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); toggle(e); }} }});
}});
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
