"""Blizzard Battle.net API client (read-only game data).

WoW: Forever's API is UNDOCUMENTED. What's known (community reports, Nov 2026):
  namespace  dynamic-forever-{region}
  houses     /data/wow/ruleset/{ruleset}/auctions/            (index, trailing slash needed)
  listings   /data/wow/ruleset/{ruleset}/auctions/{house}      -> auctions (buyout per auction)
             /data/wow/ruleset/{ruleset}/auctions/{house}/commodities -> unit_price per unit
If Blizzard changes these, this file is the only place to fix.
"""
import base64
import json
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://oauth.battle.net/token"
UA = "forever-ah-tracker/0.1 (personal project)"


class Client:
    def __init__(self, client_id, client_secret, region="eu", locale="en_GB"):
        self.region, self.locale = region, locale
        self.api = f"https://{region}.api.blizzard.com"
        self.token = self._token(client_id, client_secret)

    @staticmethod
    def _token(cid, secret):
        auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        req = urllib.request.Request(
            TOKEN_URL, data=b"grant_type=client_credentials",
            headers={"Authorization": f"Basic {auth}", "User-Agent": UA,
                     "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["access_token"]

    def get(self, path, namespace="dynamic"):
        """Returns (json, last_modified_header)."""
        q = urllib.parse.urlencode({"namespace": f"{namespace}-forever-{self.region}",
                                    "locale": self.locale})
        req = urllib.request.Request(f"{self.api}{path}?{q}", headers={
            "Authorization": f"Bearer {self.token}", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:   # houses can be ~9 MB
            return json.loads(r.read()), r.headers.get("Last-Modified")

    def house_index(self, ruleset):
        data, _ = self.get(f"/data/wow/ruleset/{ruleset}/auctions/")
        return data.get("auctions", [])

    def house(self, ruleset, house_id):
        """All listings for one house: (auctions, commodities, last_modified)."""
        base = f"/data/wow/ruleset/{ruleset}/auctions/{house_id}"
        main, lm1 = self.get(base)
        try:
            comm, lm2 = self.get(base + "/commodities")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            comm, lm2 = {}, None
        return main.get("auctions", []), comm.get("auctions", []), lm2 or lm1
