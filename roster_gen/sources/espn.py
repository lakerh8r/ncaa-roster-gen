"""ESPN data adapters: roster + per-player season stats."""
import json
import os
import re
import threading
import time

import httpx

CACHE_DIR = os.environ.get("ROSTER_CACHE", "/tmp/opencode/roster_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

UA = "Mozilla/5.0"

STATS_TTL = 86400 * 7
MISSING_TTL = 86400  # retry players with no stats page once a day

# One pooled client for the whole process: keep-alive avoids a TLS handshake
# per request, and the shared pool is safe to use from worker threads.
_CLIENT = None
_CLIENT_LOCK = threading.Lock()

# In-process cache so a player/roster is not re-read from disk in the same run.
_MEM = {}
_MEM_LOCK = threading.Lock()


class _NotFound(Exception):
    """ESPN returned 404: the resource does not exist (permanent, do not retry)."""


def _client():
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = httpx.Client(
                    timeout=30,
                    headers={"User-Agent": UA},
                    limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
                    follow_redirects=True,
                )
    return _CLIENT


def _fetch_json(url, attempts=3):
    """GET JSON, retrying only transient failures.

    Returns None when the request failed for a retryable reason, raises
    _NotFound on HTTP 404 so the caller can cache a permanent miss.
    """
    client = _client()
    for attempt in range(attempts):
        try:
            r = client.get(url)
        except (httpx.TimeoutException, httpx.TransportError):
            if attempt == attempts - 1:
                return None
            time.sleep(min(4.0, 2.0 ** attempt))
            continue

        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                return None
        if r.status_code == 404:
            raise _NotFound(url)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
            delay = None
            retry_after = r.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = None
            time.sleep(min(10.0, delay if delay is not None else 2.0 ** attempt))
            continue
        return None
    return None


def _cache_path(key):
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)
    return os.path.join(CACHE_DIR, safe + ".json")


def _write_cache(path, data, missing):
    payload = {"_ts": time.time(), "data": data}
    if missing:
        payload["_missing"] = True
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, path)  # atomic: a killed run never leaves a half file
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _cached(key, fetcher, ttl=STATS_TTL, missing_ttl=MISSING_TTL):
    """Disk + memory cache. Empty results are cached too (as a miss)."""
    with _MEM_LOCK:
        hit = _MEM.get(key)
    if hit is not None:
        return hit

    path = _cache_path(key)
    if os.path.exists(path):
        try:
            with open(path) as f:
                obj = json.load(f)
            age = time.time() - obj.get("_ts", 0)
            use_ttl = missing_ttl if obj.get("_missing") else ttl
            if age < use_ttl:
                data = obj.get("data")
                data = {} if data is None else data
                with _MEM_LOCK:
                    _MEM[key] = data
                return data
        except Exception:
            pass

    try:
        data = fetcher()
    except _NotFound:
        data = {}
    if data is None:  # transient failure: do not cache
        return {}
    if not isinstance(data, (dict, list)):
        data = {}

    _write_cache(path, data, missing=not data)
    with _MEM_LOCK:
        _MEM[key] = data
    return data


def espn_teams():
    """Return list of {id, name, abbreviation, location} for all CFB teams."""
    def fetch():
        d = _fetch_json("https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams?limit=1000")
        if not d:
            return None
        out = []
        for t in d.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
            team = t.get("team", {})
            out.append({
                "id": team.get("id"),
                "name": team.get("displayName"),
                "abbr": team.get("abbreviation"),
                "loc": team.get("location"),
            })
        return out
    return _cached("espn_teams", fetch, ttl=86400 * 30)


def espn_team_roster(espn_team_id):
    """Return list of player dicts from ESPN roster API."""
    def fetch():
        d = _fetch_json(
            f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/{espn_team_id}/roster"
        )
        if not d:
            return None
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
        return out
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

    Uses ESPN's JSON API (13KB). Players without a stats page (404) are cached
    as a miss for MISSING_TTL instead of being retried on every run.
    """
    if not espn_id:
        return {}
    url = f"https://site.web.api.espn.com/apis/common/v3/sports/football/college-football/athletes/{espn_id}/stats"

    def fetch():
        d = _fetch_json(url)
        if d is None:
            return None
        return _parse_player_stats_json(d)

    return _cached(f"stats_{espn_id}", fetch)


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
