"""Map NCAA 14 team names to ESPN team ids."""
import difflib
from roster_gen.sources.espn import espn_teams


def _norm(s):
    s = (s or "").lower()
    for tok in ["university", "college", "of", "the", "at", "&"]:
        s = s.replace(tok, " ")
    return " ".join(s.split())


# Explicit aliases for names that fuzzy/normalized matching gets wrong.
ALIASES = {
    "Miami University": "Miami (OH) RedHawks",
    "ECU": "East Carolina Pirates",
    "Mid Tenn State": "Middle Tennessee Blue Raiders",
    "San Jose State": "San José State Spartans",
    "UL Lafayette": "Louisiana Ragin' Cajuns",
    "USF": "South Florida Bulls",
    "FIU": "Florida International Panthers",
    "SMU": "SMU Mustangs",
}


def build_team_map(ncaa_names):
    teams = espn_teams()
    # index by normalized name and location
    by_name = {_norm(t["name"]): t for t in teams}
    by_loc = {_norm(t["loc"]): t for t in teams}
    result = {}
    for name in ncaa_names:
        # 0. explicit alias
        if name in ALIASES:
            alias_norm = _norm(ALIASES[name])
            for t in teams:
                if _norm(t["name"]) == alias_norm or _norm(t["loc"]) == alias_norm:
                    result[name] = t["id"]
                    break
            if name in result:
                continue
        n = _norm(name)
        # 1. exact normalized match on full ESPN name
        best_id = None
        for t in teams:
            if _norm(t["name"]) == n or _norm(t["loc"]) == n:
                best_id = t["id"]
                break
        if best_id is not None:
            result[name] = best_id
            continue
        # 2. All words of NCAA name appear in ESPN name/location
        nwords = n.split()
        candidates = []
        for t in teams:
            tn = _norm(t["name"])
            tl = _norm(t["loc"])
            if all(w in tn.split() or w in tl.split() for w in nwords):
                candidates.append(t)
        # also handle single-word NCAA names matching a multi-word ESPN name
        # only if the NCAA word is the location or first word
        if not candidates and len(nwords) == 1:
            for t in teams:
                tn = _norm(t["name"])
                tl = _norm(t["loc"])
                if n == tl or tn.startswith(n + " "):
                    candidates.append(t)
        if len(candidates) == 1:
            result[name] = candidates[0]["id"]
            continue
        if len(candidates) > 1:
            # prefer the shortest ESPN name (most specific match)
            candidates.sort(key=lambda t: len(_norm(t["name"])))
            result[name] = candidates[0]["id"]
            continue
        # 3. fuzzy fallback
        best = None
        best_score = 0.0
        for t in teams:
            score = difflib.SequenceMatcher(None, n, _norm(t["name"])).ratio()
            if score > best_score:
                best_score = score
                best = t
        # Require a strong fuzzy match; otherwise leave unmatched (kept as base).
        threshold = 0.7 if len(nwords) == 1 else 0.85
        if best is not None and best_score >= threshold:
            result[name] = best["id"]
        else:
            result[name] = None
    return result