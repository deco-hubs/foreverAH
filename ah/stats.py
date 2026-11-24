"""Turns raw listings into one price summary per item.

Prices are in copper (1g = 100s = 10 000c), as Blizzard sends them.
  min     cheapest unit price listed
  market  average unit price of the cheapest 15% of units listed (at least 1 unit).
          Close to what you'd actually pay for a normal quantity, and not thrown off
          by one silly-cheap or absurdly expensive listing. Similar idea to TSM's market value.
  qty     total units listed
"""
import math
from collections import defaultdict

MARKET_SHARE = 0.15
LEET = 1337   # 13s 37c. You know why.


def unit_listings(auctions, commodities):
    """{item_id: [(unit_price, qty), ...]} from both endpoints."""
    out = defaultdict(list)
    for a in commodities:
        price, qty = a.get("unit_price"), a.get("quantity", 0)
        if price and qty:
            out[a["item"]["id"]].append((price, qty))
    for a in auctions:
        buyout, qty = a.get("buyout"), a.get("quantity", 0)
        if buyout and qty:   # bid-only auctions have no buyout: skipped
            out[a["item"]["id"]].append((buyout / qty, qty))
    return out


def summarize(listings):
    listings = sorted(listings)
    total = sum(q for _, q in listings)
    want = max(1, math.ceil(total * MARKET_SHARE))
    taken = cost = 0
    for price, qty in listings:
        take = min(qty, want - taken)
        cost += price * take
        taken += take
        if taken >= want:
            break
    return {"min": round(listings[0][0]), "market": round(cost / taken), "qty": total}


def gold(copper):
    """12345 -> '1g 23s 45c'; small values drop the empty units."""
    if copper is None:
        return "–"
    sign = "-" if copper < 0 else ""
    c = int(round(abs(copper)))
    g, s, c = c // 10000, (c // 100) % 100, c % 100
    if g >= 100:
        return f"{sign}{g:,}g".replace(",", " ")       # 1 250g, not 1 250g 3s 7c
    if g:
        return f"{sign}{g}g {s}s" if s else f"{sign}{g}g"
    if s:
        return f"{sign}{s}s {c}c" if c else f"{sign}{s}s"
    return f"{sign}{c}c"


def coins(copper):
    """Like gold(), but as HTML with coin icons, the way the game shows money."""
    if copper is None:
        return '<span class="muted">–</span>'
    sign = "−" if copper < 0 else ""
    c = int(round(abs(copper)))
    g, s, k = c // 10000, (c // 100) % 100, c % 100
    part = lambda n, kind: f'{n:,}'.replace(",", "\u202f") + f'<i class="coin {kind}" aria-label="{kind}"></i>'
    if g >= 100:
        parts = [part(g, "gold")]
    elif g:
        parts = [part(g, "gold")] + ([part(s, "silver")] if s else [])
    elif s:
        parts = [part(s, "silver")] + ([part(k, "copper")] if k else [])
    else:
        parts = [part(k, "copper")]
    if c == LEET:
        return f'<span class="money leet" title="1337">{sign}{" ".join(parts)}</span>'
    return f'<span class="money">{sign}{" ".join(parts)}</span>'
