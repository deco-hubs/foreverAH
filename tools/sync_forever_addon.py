"""Installs and updates the Forever Net Worth addon, with fresh auction house prices.

Run it on the PC where WoW: Forever is installed. It downloads the addon files and the latest
Prices.lua (written by the tracker on GitHub) into the game's AddOns folder. The game reads the
new prices the next time you log in or type /reload.

    python sync_forever_addon.py                      finds the AddOns folder by itself
    python sync_forever_addon.py "D:\\Games\\World of Warcraft\\_forever_\\Interface\\AddOns"

The folder you pass (or the one it finds) is remembered in sync_forever_addon.json next to this
script. Python 3.8+ standard library only. It only downloads files; it never touches your
SavedVariables, so your net worth history is safe.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("FNW_BASE_URL", "https://deco-hubs.github.io/foreverAH/addon/")   # change after the Cloudflare move
ADDON = "ForeverNetWorth"
HERE = Path(__file__).resolve().parent
SETTINGS = HERE / "sync_forever_addon.json"
LOG = HERE / "sync_forever_addon.log"

GUESSES = [
    r"C:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns",
    r"C:\Program Files\World of Warcraft\_forever_\Interface\AddOns",
    r"D:\World of Warcraft\_forever_\Interface\AddOns",
    r"D:\Games\World of Warcraft\_forever_\Interface\AddOns",
    r"D:\Program Files (x86)\World of Warcraft\_forever_\Interface\AddOns",
    r"E:\World of Warcraft\_forever_\Interface\AddOns",
]


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def find_addons_dir(arg):
    if arg:
        p = Path(arg)
    elif SETTINGS.exists():
        p = Path(json.loads(SETTINGS.read_text(encoding="utf-8"))["addons_dir"])
    else:
        p = next((Path(g) for g in GUESSES if Path(g).parent.parent.exists()), None)
        if p is None:
            sys.exit("Couldn't find WoW: Forever. Run it again with the AddOns folder, e.g.\n"
                     '  python sync_forever_addon.py "C:\\Program Files (x86)\\World of Warcraft\\_forever_\\Interface\\AddOns"\n'
                     "Tip: in the Battle.net app, the cog next to Play > Show in Explorer opens the game folder.")
    if p.name.lower() != "addons":                 # accept the game folder or _forever_ too
        if (p / "_forever_").exists():
            p = p / "_forever_"
        p = p / "Interface" / "AddOns"
    p.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps({"addons_dir": str(p)}, indent=1), encoding="utf-8")
    return p


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ForeverNetWorth-sync", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    addons = find_addons_dir(sys.argv[1] if len(sys.argv) > 1 else None)
    target = addons / ADDON
    target.mkdir(exist_ok=True)
    stamp = f"?t={int(time.time())}"          # skip any stale cache
    manifest = json.loads(get(BASE_URL + "manifest.json" + stamp))
    for name in manifest["files"]:
        data = get(f"{BASE_URL}{ADDON}/{name}{stamp}")
        tmp = target / (name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target / name)             # swap in one go, never a half-written file
    log(f"Updated {ADDON} in {target}: {manifest.get('items', '?')} prices from {manifest.get('prices_updated', '?')} UTC. "
        "In game: /reload (or log in) to load them.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:                     # keep a record when it runs unattended from Task Scheduler
        log(f"FAILED: {e}")
        sys.exit(1)
