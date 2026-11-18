"""Reads config.toml. Secrets come from environment variables, never from files in the repo."""
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"      # hourly price history, committed by the workflow
DOCS = ROOT / "docs"      # the dashboard, served by GitHub Pages


def load(path=ROOT / "config.toml"):
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    cfg["items"] = cfg.get("materials", {}).get("items", [])
    if not cfg["items"]:
        raise SystemExit("config.toml: no items found under [materials]")
    cfg.setdefault("recipe", [])
    seen = set()
    for item in cfg["items"]:
        if item["id"] in seen:
            raise SystemExit(f"config.toml: item id {item['id']} is listed twice")
        seen.add(item["id"])
    DATA.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    return cfg


def secrets():
    cid, secret = os.environ.get("BNET_CLIENT_ID"), os.environ.get("BNET_CLIENT_SECRET")
    if not cid or not secret:
        raise SystemExit("Missing BNET_CLIENT_ID / BNET_CLIENT_SECRET. In GitHub: Settings -> "
                         "Secrets and variables -> Actions. Locally: set them as environment variables.")
    return cid, secret
