"""Scrape ESPN's AP Top 25 and Coaches Poll."""
import re
import httpx
from bs4 import BeautifulSoup

from roster_gen.sources.espn import _cached


def _espn_id_from_uid(uid):
    if not uid:
        return None
    m = re.search(r"t:(\d+)", uid)
    return m.group(1) if m else None


def _parse_rankings_table(table):
    """Return {espn_team_id: rank} from an ESPN rankings table."""
    result = {}
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        rank_text = tds[0].get_text(strip=True)
        if not rank_text.isdigit():
            continue
        rank = int(rank_text)
        link = tr.find("a", attrs={"data-clubhouse-uid": True})
        if link:
            tid = _espn_id_from_uid(link.get("data-clubhouse-uid"))
        else:
            a = tr.find("a", href=True)
            if a:
                m = re.search(r"/id/(\d+)/", a.get("href", ""))
                tid = m.group(1) if m else None
            else:
                tid = None
        if tid:
            result[tid] = rank
    return result


def fetch_rankings():
    """Return {'ap': {espn_id: rank}, 'coaches': {espn_id: rank}}."""
    def fetch():
        r = httpx.get("https://www.espn.com/college-football/rankings",
                      timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        tables = soup.find_all("table")
        ap = _parse_rankings_table(tables[0]) if len(tables) >= 1 else {}
        coaches = _parse_rankings_table(tables[1]) if len(tables) >= 2 else {}
        return {"ap": ap, "coaches": coaches}
    return _cached("rankings", fetch, ttl=3600)


def build_ranking_map(ncaa_to_espn):
    """Given {ncaa_name: espn_id}, return {ncaa_name: (ap_rank, coaches_rank)}.

    Unranked teams get (0, 0).
    """
    rankings = fetch_rankings()
    ap = rankings.get("ap", {})
    coaches = rankings.get("coaches", {})
    result = {}
    for name, espn_id in ncaa_to_espn.items():
        if espn_id is None:
            result[name] = (0, 0)
            continue
        result[name] = (ap.get(espn_id, 0), coaches.get(espn_id, 0))
    return result