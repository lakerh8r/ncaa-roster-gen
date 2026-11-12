"""ESPN data adapters: roster + per-player season stats."""
import json
import os
import re
import time
import httpx
from bs4 import BeautifulSoup

CACHE_DIR = os.environ.get("ROSTER_CACHE", "/tmp/opencode/roster_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


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
    try:
        json.dump({"_ts": time.time(), "data": data}, open(path, "w"))
    except Exception:
        pass
    return data


def espn_teams():
    """Return list of {id, name, abbreviation, location} for all CFB teams."""
    def fetch():
        r = httpx.get("https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams?limit=500", timeout=30)
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
        r = httpx.get(f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/{espn_team_id}/roster", timeout=30)
        r.raise_for_status()
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
                    "pos": (it.get("position") or {}).get("abbreviation", ""),
                    "jersey": it.get("jersey"),
                    "height": it.get("height"),
                    "weight": it.get("weight"),
                    "experience": exp.get("years", 0),
                    "class": exp.get("abbreviation", ""),
                })
        return out
    return _cached(f"roster_{espn_team_id}", fetch, ttl=86400 * 7)


def _parse_player_stats_html(html):
    """Parse ESPN player stats page into {season: {category: {stat: value}}}."""
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    # tables come in pairs: season/Team table + stats table
    result = {}
    # collect season rows from the first table of each pair
    i = 0
    n = len(tables)
    # Strategy: find all tables; identify "season" header tables
    # Pair consecutive tables: season table then stats table
    idx = 0
    # gather (season_table, stats_table) pairs
    pairs = []
    # ESPN layout: season table, stats table, season table, stats table, ...
    # Detect by header containing 'season'
    cur_season = None
    cur_stats = None
    for t in tables:
        headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
        if "season" in headers:
            # this is a season table; finalize previous pair
            if cur_season is not None and cur_stats is not None:
                pairs.append((cur_season, cur_stats))
            cur_season = t
            cur_stats = None
        else:
            if cur_season is not None:
                cur_stats = t
    if cur_season is not None and cur_stats is not None:
        pairs.append((cur_season, cur_stats))

    for st, ss in pairs:
        # season rows
        seasons = []
        for tr in st.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells and cells[0] and cells[0].lower() not in ("career",):
                seasons.append(cells[0])
            elif cells and cells[0].lower() == "career":
                seasons.append("Career")
        # stats rows
        stat_headers = [th.get_text(strip=True) for th in ss.find_all("th")]
        stat_rows = []
        for tr in ss.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                stat_rows.append(cells)
        # align
        # sometimes there's a leading empty header row; handle by length
        for si, season in enumerate(seasons):
            if si >= len(stat_rows):
                break
            row = stat_rows[si]
            # map headers to values
            vals = {}
            for hi, h in enumerate(stat_headers):
                if hi < len(row):
                    v = row[hi].replace(",", "")
                    try:
                        vals[h] = float(v)
                    except ValueError:
                        vals[h] = v
            result[season] = vals
    return result


def espn_player_stats(espn_id):
    """Return {season: {statname: value}} for a player (career + per season)."""
    def fetch():
        url = f"https://www.espn.com/college-football/player/stats/_/id/{espn_id}"
        r = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": UA})
        r.raise_for_status()
        return _parse_player_stats_html(r.text)
    return _cached(f"stats_{espn_id}", fetch, ttl=86400 * 7)


# position mapping: ESPN abbreviations -> NCAA 14 codes
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
    "LS": 4,  # long snapper -> TE in PLAY
    "ATH": None,  # resolved later
}


def map_position(espn_pos, weight=None):
    code = ESPN_POS_MAP.get(espn_pos)
    if code is not None:
        return code
    # EDGE by size
    if espn_pos in ("EDGE", "ER"):
        return 10 if (weight or 0) >= 250 else 11
    # ATH: default to WR, resolved later by need
    if espn_pos == "ATH":
        return 3
    return None