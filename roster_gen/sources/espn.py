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
    # Don't cache empty results (likely rate-limited or failed)
    if data:
        try:
            json.dump({"_ts": time.time(), "data": data}, open(path, "w"))
        except Exception:
            pass
    return data


def espn_teams():
    """Return list of {id, name, abbreviation, location} for all CFB teams."""
    def fetch():
        r = httpx.get("https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams?limit=1000", timeout=30)
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


def _parse_player_stats_html(html):
    """Parse ESPN player stats page into {season: {category: {stat: value}}}."""
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    # tables come in pairs: season/Team table + stats table
    result = {}
    # collect season rows from the first table of each pair
    i = 0
    n = len(tables)
    # Strategy: pair adjacent tables where first has 'season' in headers
    # and second does not. Skip standings tables (no stat-like columns).
    pairs = []
    i = 0
    while i < len(tables) - 1:
        h1 = [th.get_text(strip=True).lower() for th in tables[i].find_all("th")]
        h2 = [th.get_text(strip=True).lower() for th in tables[i + 1].find_all("th")]
        if "season" in h1 and "season" not in h2:
            # make sure h2 has actual stat columns (not just team/conf/ovr)
            skip_words = {"team", "conf", "ovr", "rk", ""}
            stat_cols = [h for h in h2 if h not in skip_words]
            if len(stat_cols) >= 2:
                pairs.append((tables[i], tables[i + 1]))
                i += 2
                continue
        i += 1

    # Header mapping per pair index (ESPN uses ambiguous abbreviations).
    # Pairs are in order: passing, rushing, receiving, defense, scoring.
    PAIR_HEADER_MAP = [
        # Pair 0: passing
        {"CMP": "completions", "ATT": "passingAttempts", "CMP%": "completionPct",
         "YDS": "passingYards", "AVG": "yardsPerAttempt", "TD": "passingTouchdowns",
         "INT": "interceptions", "LNG": "longPass", "SACK": "sacks", "RTG": "rating"},
        # Pair 1: rushing
        {"CAR": "rushingAttempts", "YDS": "rushingYards", "AVG": "yardsPerRushAttempt",
         "TD": "rushingTouchdowns", "LNG": "longRushing"},
        # Pair 2: receiving
        {"REC": "receptions", "YDS": "receivingYards", "AVG": "yardsPerReception",
         "TD": "receivingTouchdowns", "LNG": "longReception"},
        # Pair 3: defense
        {"TOT": "tackles", "SOLO": "soloTackles", "AST": "assistedTackles",
         "PD": "passesDefended", "SACK": "sacks", "FF": "forcedFumbles",
         "INT": "interceptions", "YDS": "interceptionYards", "TD": "defTD"},
        # Pair 4: scoring summary
        {"PASS": "passingTD", "RUSH": "rushingTD", "REC": "receivingTD",
         "RET": "returnTD", "TD": "totalTD", "2PT": "twoPt", "PAT": "pat",
         "FG": "fg", "PTS": "points"},
    ]
    for pair_idx, (st, ss) in enumerate(pairs):
        hmap = PAIR_HEADER_MAP[pair_idx] if pair_idx < len(PAIR_HEADER_MAP) else {}
        # season rows
        seasons = []
        for tr in st.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells and len(cells) >= 1 and cells[0] and cells[0].lower() not in ("career",):
                seasons.append(cells[0])
            elif cells and len(cells) >= 1 and cells[0].lower() == "career":
                seasons.append("Career")
        # stats rows
        stat_headers = [th.get_text(strip=True) for th in ss.find_all("th")]
        stat_rows = []
        for tr in ss.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells and any(c.strip() for c in cells):
                stat_rows.append(cells)
        # align
        for si, season in enumerate(seasons):
            if si >= len(stat_rows):
                break
            row = stat_rows[si]
            vals = {}
            for hi, h in enumerate(stat_headers):
                if hi < len(row) and h.strip():
                    v = row[hi].replace(",", "")
                    try:
                        num = float(v)
                    except ValueError:
                        num = None
                    # map to standardized key
                    key = hmap.get(h, h)
                    if num is not None:
                        vals[key] = num
            if vals:
                result.setdefault(season, {}).update(vals)
    return result


def espn_player_stats(espn_id, slug=None):
    """Return {season: {statname: value}} for a player (career + per season)."""
    if slug:
        url = f"https://www.espn.com/college-football/player/stats/_/id/{espn_id}/{slug}"
    else:
        url = f"https://www.espn.com/college-football/player/stats/_/id/{espn_id}"
    def fetch():
        for attempt in range(3):
            try:
                r = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": UA})
                if r.status_code == 200 and len(r.text) > 1000:
                    return _parse_player_stats_html(r.text)
                if r.status_code == 202:
                    time.sleep(1 + attempt)
                    continue
                r.raise_for_status()
            except Exception:
                time.sleep(1 + attempt)
        return {}
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