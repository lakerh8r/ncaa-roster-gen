"""ESPN data adapters: roster + per-player season stats."""
import json
import os
import re
import time
import httpx
from bs4 import BeautifulSoup

CACHE_DIR = os.environ.get("ROSTER_CACHE", "/tmp/opencode/roster_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

UA = "Mozilla/5.0"


def _cache_path(key):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)
    return os.path.join(CACHE_DIR, safe + ".json")


def _cached(key, fetcher, ttl=86400 * 7):
    path = _cache_path(key)
    if os.path.exists(path):
        try:
            obj = json.load(open(path))
            if time.time() - obj.get("_ts", 0) < ttl:
                return obj["data"]
        except Exception:
            pass
    data = fetcher()
    if data:
        try:
            json.dump({"_ts": time.time(), "data": data}, open(path, "w"))
        except Exception:
            pass
    return data


def espn_teams():
    """Return list of {id, name, abbreviation, location} for all CFB teams."""
    def fetch():
        r = httpx.get("https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams?limit=1000", timeout=30, headers={"User-Agent": UA})
        r.raise_for_status()
        d = r.json()
        out = []
        for t in d.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
            team = t.get("team", {})
            out.append({"id": team.get("id"), "name": team.get("displayName"), "abbr": team.get("abbreviation"), "loc": team.get("location")})
        return out
    return _cached("espn_teams", fetch, ttl=86400 * 30)


def espn_team_roster(espn_team_id):
    """Return list of player dicts from ESPN roster API."""
    def fetch():
        for attempt in range(3):
            try:
                r = httpx.get(f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/{espn_team_id}/roster", timeout=30, headers={"User-Agent": UA})
                if r.status_code == 200:
                    d = r.json()
                    out = []
                    for g in d.get("athletes", []):
                        for it in g.get("items", []):
                            exp = it.get("experience", {}) or {}
                            out.append({
                                "espn_id": it.get("id"),
                                "first": it.get("firstName", ""),
                                "last": it.get("lastName", ""),
                                "name": it.get("displayName", ""),
                                "slug": it.get("slug", ""),
                                "pos": (it.get("position") or {}).get("abbreviation", ""),
                                "jersey": it.get("jersey"),
                                "height": it.get("height"),
                                "weight": it.get("weight"),
                                "experience": exp.get("years", 0),
                                "class": exp.get("abbreviation", ""),
                                "status": (it.get("status") or {}).get("type", "active"),
                            })
                    if out:
                        return out
                time.sleep(1 + attempt)
            except Exception:
                time.sleep(1 + attempt)
        return []
    return _cached(f"roster_{espn_team_id}", fetch, ttl=86400 * 3)


def _parse_player_stats_json(d):
    """Parse ESPN's JSON stats API response into {season: {stat: value}}."""
    result = {}
    for cat in d.get("categories", []):
        names = cat.get("names", [])
        for entry in cat.get("statistics", []):
            season_year = entry.get("season", {}).get("year")
            if season_year is None:
                continue
            season_key = str(season_year)
            stats = entry.get("stats", [])
            vals = {}
            for i, name in enumerate(names):
                if i < len(stats):
                    v = stats[i]
                    try:
                        vals[name] = float(str(v).replace(",", ""))
                    except (ValueError, TypeError):
                        vals[name] = v
            # Skip passing sacks (ambiguous with defensive sacks)
            if "sacks" in vals and cat.get("name") == "passing":
                del vals["sacks"]
            if vals:
                result.setdefault(season_key, {}).update(vals)
    return result


def espn_player_stats(espn_id, slug=None):
    """Return {season: {statname: value}} for a player (career + per season).

    Uses ESPN's JSON API (13KB) instead of HTML scraping (500KB).
    """
    url = f"https://site.web.api.espn.com/apis/common/v3/sports/football/college-football/athletes/{espn_id}/stats"
    def fetch():
        for attempt in range(3):
            try:
                r = httpx.get(url, timeout=30, headers={"User-Agent": UA})
                if r.status_code == 200:
                    d = r.json()
                    result = _parse_player_stats_json(d)
                    if result:
                        return result
                time.sleep(1 + attempt)
            except Exception:
                time.sleep(1 + attempt)
        return {}
    return _cached(f"stats_{espn_id}", fetch, ttl=86400 * 7)


# Position mapping: ESPN abbreviations -> NCAA 14 codes
ESPN_POS_MAP = {
    "QB": 0,
    "RB": 1, "HB": 1,
    "FB": 2,
    "WR": 3,
    "TE": 4,
    "OT": 5, "LT": 5,
    "OG": 6, "LG": 6, "G": 6,
    "C": 7,
    "RG": 8,
    "RT": 9,
    "DE": 10, "LE": 10, "RE": 11,
    "DT": 12, "NT": 12,
    "LB": 13, "OLB": 13, "ILB": 14, "MLB": 14,
    "CB": 16,
    "S": 17, "FS": 17, "SS": 18,
    "K": 19, "PK": 19,
    "P": 20,
    "LS": 4,
    "ATH": None,
}


def map_position(espn_pos, weight=None):
    code = ESPN_POS_MAP.get(espn_pos)
    if code is not None:
        return code
    if espn_pos in ("EDGE", "ER"):
        return 10 if (weight or 0) >= 250 else 11
    if espn_pos == "ATH":
        return 3
    return None