"""Price history as plain CSV, one file per month: data/2026-11.csv.

One row per tracked item per snapshot:
  time_utc,item_id,min,market,qty
Plain text so GitHub shows small diffs, Excel opens it, and nothing can corrupt a database.
"""
import csv
import json
from datetime import datetime, timedelta, timezone

from .config import DATA

FIELDS = ["time_utc", "item_id", "min", "market", "qty"]
STATE = DATA / "state.json"


def load_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(state):
    STATE.write_text(json.dumps(state, indent=2) + "\n")


def append(time_utc, summaries):
    path = DATA / f"{time_utc[:7]}.csv"
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(FIELDS)
        for item_id, s in sorted(summaries.items()):
            w.writerow([time_utc, item_id, s["min"], s["market"], s["qty"]])
    return path


def load(days=60, now=None):
    """{item_id: [(datetime, min, market, qty), ...]} oldest first, for the last `days` days."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    out = {}
    for path in sorted(DATA.glob("????-??.csv")):
        if path.stem < since.strftime("%Y-%m"):
            continue
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                t = datetime.fromisoformat(r["time_utc"].replace("Z", "+00:00"))
                if t >= since:
                    out.setdefault(int(r["item_id"]), []).append(
                        (t, int(r["min"]), int(r["market"]), int(r["qty"])))
    for rows in out.values():
        rows.sort()
    return out
