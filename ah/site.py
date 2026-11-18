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

def build(cfg, hist, latest_time, out_path):
    ah = cfg["auction_house"]
    names = {i["id"]: i["name"] for i in cfg["items"]}
    now = latest_time
    current, rows_html, never_seen, chart_data = {}, {}, [], {}

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
        change_cells = "".join(f'<td class="num">{_pct_html(c, need)}</td>'
                               for c, need in zip(changes, ("1 day", "7 days", "1 month", "3 months", "6 months")))
        rows_html.setdefault(item.get("category", "Other"), []).append(f"""
<tr class="item" data-id="{iid}" tabindex="0" title="Click for the price chart">
  <td><a href="https://www.wowhead.com/forever/item={iid}" target="_blank" rel="noopener">{name}</a>{status}</td>
  <td class="num"><b>{gold(last[2])}</b><div class="small muted">min {gold(last[1])}</div></td>
  <td class="num">{last[3]:,}</td>
  <td class="num">{gold(avg7)}</td>
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
<table><thead><tr><th>Item</th><th class="num">Market value</th><th class="num">Listed</th><th class="num">7-day avg</th>
<th class="num">24 h</th><th class="num">7 d</th><th class="num">1 m</th><th class="num">3 m</th><th class="num">6 m</th><th>Last 7 days</th></tr></thead>
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
.ranges {{ display:flex; gap:6px; margin-bottom:8px; }}
.ranges button {{ font:inherit; font-size:12px; padding:3px 10px; border:1px solid var(--line); border-radius:6px; background:transparent; color:var(--muted); cursor:pointer; }}
.ranges button.on {{ color:var(--fg); border-color:var(--accent); }}
th:nth-child(n+5):nth-child(-n+9) {{ width:52px; }}
@media (max-width:900px) {{ th:nth-child(4), td:nth-child(4), .spark-cell, th:last-child {{ display:none; }} }}
@media (max-width:640px) {{ th:nth-child(3), td:nth-child(3), th:nth-child(8), td:nth-child(8), th:nth-child(9), td:nth-child(9) {{ display:none; }} }}
</style></head><body><main>
<h1>Forever auction house</h1>
<p class="sub">{html.escape(ah['region'].upper())} · ruleset {ah['ruleset']} · Horde (house {ah['house_id']}) · snapshot <time data-utc="{now.isoformat()}">{now.strftime('%d %b %Y %H:%M')} UTC</time></p>
<p class="small muted">Market value = average price of the cheapest 15% of units listed. 24 h compares with the snapshot a day ago; 7 d to 6 m compare with that day's average price. "–" means not enough history yet. Click any row for its chart.</p>
{craft_html}
{sections}
{flagged}
<p class="small muted" style="margin-top:40px">Data: Blizzard Battle.net API (undocumented WoW: Forever endpoints), updated hourly by GitHub Actions. Item names link to Wowhead's WoW: Forever database.</p>
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
