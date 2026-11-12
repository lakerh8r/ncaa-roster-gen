"""Map NCAA 14 team names to ESPN team ids."""
import difflib
from roster_gen.sources.espn import espn_teams


def _norm(s):
    s = (s or "").lower()
    for tok in ["university", "state", "college", "of", "the", "at", "&"]:
        s = s.replace(tok, " ")
    return " ".join(s.split())


def build_team_map(ncaa_names):
    """Return {ncaa_name: espn_team_id or None}."""
    teams = espn_teams()
    # index by normalized name
    by_norm = {_norm(t["name"]): t for t in teams}
    by_loc = {_norm(t["loc"]): t for t in teams}
    result = {}
    for name in ncaa_names:
        n = _norm(name)
        if n in by_norm:
            result[name] = by_norm[n]["id"]
            continue
        if n in by_loc:
            result[name] = by_loc[n]["id"]
            continue
        # fuzzy
        best = None
        best_score = 0.0
        for t in teams:
            score = difflib.SequenceMatcher(None, n, _norm(t["name"])).ratio()
            if score > best_score:
                best_score = score
                best = t
        if best_score >= 0.6:
            result[name] = best["id"]
        else:
            result[name] = None
    return result
