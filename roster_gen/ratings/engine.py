"""Rating engine: turn roster + stats into NCAA 14 attribute dicts.

Implements ratings_spec.md in a pragmatic, defensible way. All formulas are
pure functions of inputs; weights live in formulas.yaml (defaults here).
"""
import math
import statistics

# Position-specific OVR weights (attribute -> weight). Attributes not listed = 0.
OVR_WEIGHTS = {
    0: {"PTHP": 0.18, "PTHA": 0.22, "PAWR": 0.18, "PSPD": 0.10, "PACC": 0.08, "PAGI": 0.06, "PSTR": 0.04, "PCAR": 0.04, "PBTK": 0.03, "PTRK": 0.03, "RELS": 0.04},
    1: {"PSPD": 0.16, "PACC": 0.12, "PAGI": 0.10, "PSTR": 0.06, "PCAR": 0.10, "PBTK": 0.08, "PTRK": 0.06, "PESV": 0.08, "PJMV": 0.06, "PSMV": 0.06, "PBCV": 0.06, "PCTH": 0.06},
    3: {"PSPD": 0.18, "PACC": 0.12, "PAGI": 0.10, "PCTH": 0.14, "TRAF": 0.08, "SPCT": 0.08, "PRTR": 0.10, "RELS": 0.08, "PJMP": 0.06, "PSTR": 0.06},
    4: {"PCTH": 0.14, "PRTR": 0.12, "RELS": 0.10, "PPBK": 0.12, "PRBK": 0.12, "PSTR": 0.12, "PSPD": 0.10, "PAGI": 0.08, "PBSH": 0.10},
}
# generic fallback for positions not explicitly listed
DEFAULT_OVR_WEIGHTS = {"PSPD": 0.12, "PACC": 0.10, "PAGI": 0.08, "PSTR": 0.12, "PAWR": 0.15, "PTAK": 0.12, "PBSH": 0.10, "PPRS": 0.08, "PHIT": 0.07, "PJMP": 0.06}

OL_POSITIONS = {5, 6, 7, 8, 9}
DL_POSITIONS = {10, 11, 12}
LB_POSITIONS = {13, 14, 15}
DB_POSITIONS = {16, 17, 18}


def _clamp(v, lo=40, hi=99):
    return max(lo, min(hi, int(round(v))))


def _pct_rank(values, value):
    """Percentile rank of value within values (0..1)."""
    if not values:
        return 0.5
    s = sorted(values)
    # fraction strictly less + half of equals
    less = sum(1 for v in s if v < value)
    eq = sum(1 for v in s if v == value)
    return (less + 0.5 * eq) / len(s)


def _norm_height_inches(h):
    if h is None:
        return 72
    return int(round(h))


def _speed_estimate(pos, weight, height, experience, stats):
    # base by position
    base = {0: 78, 1: 86, 2: 78, 3: 88, 4: 78, 5: 62, 6: 62, 7: 62, 8: 62, 9: 62,
            10: 78, 11: 80, 12: 72, 13: 80, 14: 78, 15: 80, 16: 88, 17: 86, 18: 84,
            19: 70, 20: 72}.get(pos, 75)
    # weight adjustment: heavier -> slower for skill positions
    if weight and pos in (1, 3, 16, 17, 18):
        if weight > 210:
            base -= (weight - 210) // 8
        elif weight < 185:
            base += (185 - weight) // 10
    # experience small boost
    base += min(3, experience or 0)
    # production proxy: yards per touch
    ypt = None
    if stats:
        rec_yds = stats.get("receivingYards") or stats.get("YDS", 0) or 0
        car = stats.get("rushingAttempts") or stats.get("CAR", 0) or 0
        rec = stats.get("receptions") or stats.get("REC", 0) or 0
        touches = car + rec
        if touches > 0:
            ypt = ( (stats.get("rushingYards") or 0) + (stats.get("receivingYards") or 0) ) / touches
            if ypt > 12:
                base += 4
            elif ypt > 8:
                base += 2
    # caps
    cap = {5: 78, 6: 78, 7: 78, 8: 78, 9: 78, 12: 82, 19: 78, 20: 78}.get(pos, 99)
    floor = {5: 50, 6: 50, 7: 50, 8: 50, 9: 50}.get(pos, 60)
    return _clamp(base, floor, cap)


def _strength_estimate(pos, weight, experience):
    base = {0: 62, 1: 72, 2: 82, 3: 62, 4: 78, 5: 88, 6: 88, 7: 86, 8: 88, 9: 88,
            10: 84, 11: 84, 12: 86, 13: 80, 14: 82, 15: 80, 16: 62, 17: 68, 18: 70,
            19: 45, 20: 50}.get(pos, 70)
    if weight:
        base += (weight - 220) // 12
    base += min(4, experience or 0)
    cap = 99
    floor = 40
    if pos in (16, 17, 18, 3, 0, 19, 20):
        cap = 78
    return _clamp(base, floor, cap)


def _awareness_estimate(pos, experience, stats):
    base = 55 + min(20, (experience or 0) * 5)
    # production consistency proxy
    if stats:
        # games played proxy via receptions/carries
        touches = (stats.get("receptions", 0) or 0) + (stats.get("rushingAttempts", 0) or 0) + (stats.get("completions", 0) or 0)
        if touches > 50:
            base += 8
        elif touches > 20:
            base += 4
    # awards unknown -> no boost
    return _clamp(base, 45, 97)


def _production_value(pos, stats):
    """Return a single production score used for percentile ranking within position."""
    if not stats:
        return 0.0
    if pos == 0:  # QB
        yds = stats.get("passingYards", 0) or stats.get("YDS", 0) or 0
        td = stats.get("passingTouchdowns", 0) or stats.get("TD", 0) or 0
        ints = stats.get("interceptions", 0) or 0
        comp = stats.get("completions", 0) or 0
        att = stats.get("passingAttempts", 0) or stats.get("ATT", 0) or 0
        cmp_pct = (comp / att * 100) if att else 50
        return yds * 0.001 + td * 2.0 - ints * 1.5 + cmp_pct * 0.1
    if pos in (1, 2):  # RB/FB
        ry = stats.get("rushingYards", 0) or stats.get("YDS", 0) or 0
        rt = stats.get("rushingTouchdowns", 0) or stats.get("TD", 0) or 0
        car = stats.get("rushingAttempts", 0) or stats.get("CAR", 0) or 1
        rec = stats.get("receptions", 0) or 0
        rec_y = stats.get("receivingYards", 0) or 0
        return ry * 0.002 + rt * 2.0 + (rec_y * 0.001) + rec * 0.3 + (ry / car if car else 0) * 0.5
    if pos == 3:  # WR
        rec = stats.get("receptions", 0) or 0
        yds = stats.get("receivingYards", 0) or stats.get("YDS", 0) or 0
        td = stats.get("receivingTouchdowns", 0) or stats.get("TD", 0) or 0
        return rec * 0.5 + yds * 0.002 + td * 2.5
    if pos == 4:  # TE
        rec = stats.get("receptions", 0) or 0
        yds = stats.get("receivingYards", 0) or 0
        td = stats.get("receivingTouchdowns", 0) or 0
        return rec * 0.6 + yds * 0.002 + td * 2.5
    # defense / OL / K / P: use snap/experience proxy
    return (stats.get("tackles", 0) or 0) * 0.5 + (stats.get("sacks", 0) or 0) * 3.0 + (stats.get("interceptions", 0) or 0) * 4.0


def _blend_stats(cur, prior):
    """Blend current-season and prior-season stat dicts with 60/40."""
    if not cur and not prior:
        return {}
    if not cur:
        return dict(prior or {})
    if not prior:
        return dict(cur)
    out = {}
    keys = set(cur) | set(prior)
    for k in keys:
        a = cur.get(k, 0) or 0
        b = prior.get(k, 0) or 0
        # only blend numeric
        try:
            out[k] = 0.6 * float(a) + 0.4 * float(b)
        except (ValueError, TypeError):
            out[k] = a if a else b
    return out


def rate_players(players):
    """Given a list of player dicts (with 'pos', 'stats' (current), 'prior_stats',
    'experience', 'height', 'weight'), return list of (player, attr_dict)."""
    # blend stats
    for p in players:
        p["_stats"] = _blend_stats(p.get("stats", {}), p.get("prior_stats", {}))

    # compute production scores per position for percentile ranking
    by_pos = {}
    for p in players:
        by_pos.setdefault(p["pos"], []).append(p)
    prod_scores = {}
    for pos, ps in by_pos.items():
        vals = [_production_value(pos, p["_stats"]) for p in ps]
        for p, v in zip(ps, vals):
            prod_scores[id(p)] = (vals, v)

    results = []
    for p in players:
        pos = p["pos"]
        stats = p["_stats"]
        exp = p.get("experience", 0) or 0
        wt = p.get("weight", 200) or 200
        ht = p.get("height", 72) or 72
        vals, v = prod_scores[id(p)]
        pct = _pct_rank(vals, v)  # 0..1
        prod_rating = 40 + pct * 55  # 40..95

        spd = _speed_estimate(pos, wt, ht, exp, stats)
        str_ = _strength_estimate(pos, wt, exp)
        awr = _awareness_estimate(pos, exp, stats)

        attrs = {}
        # universal
        attrs["PSPD"] = spd
        attrs["PACC"] = _clamp(spd - 1 if pos not in OL_POSITIONS else spd, 40, 99)
        attrs["PAGI"] = _clamp(int(0.6 * spd + 0.4 * (70 if pos in DB_POSITIONS else 65)), 40, 99)
        attrs["PSTR"] = str_
        attrs["PSTA"] = _clamp(70 + min(20, exp * 4) + (5 if prod_rating > 70 else 0), 50, 99)
        attrs["PINJ"] = 80
        attrs["PJMP"] = _clamp(60 + (ht - 70) * 2 + (5 if pos in DB_POSITIONS else 0), 40, 99)
        attrs["PHGT"] = ht
        attrs["PWGT"] = wt - 160
        attrs["PAWR"] = awr
        attrs["PPRC"] = _clamp(awr - 3, 40, 99) if pos in DL_POSITIONS | LB_POSITIONS | DB_POSITIONS else 50

        # position-specific production attributes mapped from prod_rating
        if pos == 0:  # QB
            attrs["PTHP"] = _clamp(65 + (prod_rating - 50) * 0.4 + (5 if wt > 215 else 0), 55, 99)
            attrs["PTHA"] = _clamp(prod_rating + 5, 40, 99)
            attrs["PCAR"] = _clamp(50 + (prod_rating - 50) * 0.3, 40, 80)
            attrs["PBTK"] = _clamp(45 + (prod_rating - 50) * 0.2, 40, 75)
            attrs["PTRK"] = _clamp(45 + (prod_rating - 50) * 0.2, 40, 75)
            attrs["RELS"] = _clamp(60 + (prod_rating - 50) * 0.3, 40, 90)
        elif pos in (1, 2):  # RB/FB
            attrs["PCAR"] = _clamp(prod_rating, 40, 99)
            attrs["PBTK"] = _clamp(prod_rating - 5, 40, 95)
            attrs["PTRK"] = _clamp(prod_rating - 8, 40, 90)
            attrs["PESV"] = _clamp(prod_rating + 2, 40, 99)
            attrs["PJMV"] = _clamp(prod_rating - 3, 40, 95)
            attrs["PSMV"] = _clamp(prod_rating - 5, 40, 90)
            attrs["PBCV"] = _clamp(prod_rating - 2, 40, 95)
            attrs["PCTH"] = _clamp(55 + (prod_rating - 50) * 0.4, 40, 85)
            attrs["TRAF"] = _clamp(50 + (prod_rating - 50) * 0.3, 40, 80)
            attrs["PRTR"] = _clamp(50 + (prod_rating - 50) * 0.3, 40, 80)
        elif pos == 3:  # WR
            attrs["PCTH"] = _clamp(prod_rating + 5, 40, 99)
            attrs["TRAF"] = _clamp(prod_rating, 40, 95)
            attrs["SPCT"] = _clamp(prod_rating - 5, 40, 95)
            attrs["PRTR"] = _clamp(prod_rating, 40, 95)
            attrs["RELS"] = _clamp(prod_rating - 2, 40, 90)
            attrs["PESV"] = _clamp(prod_rating - 10, 40, 85)
            attrs["PJMV"] = _clamp(prod_rating - 12, 40, 85)
            attrs["PSMV"] = _clamp(prod_rating - 15, 40, 80)
        elif pos == 4:  # TE
            attrs["PCTH"] = _clamp(prod_rating + 3, 40, 95)
            attrs["PRTR"] = _clamp(prod_rating - 2, 40, 90)
            attrs["RELS"] = _clamp(prod_rating - 5, 40, 85)
            attrs["PPBK"] = _clamp(str_ - 2, 40, 95)
            attrs["PRBK"] = _clamp(str_ - 2, 40, 95)
            attrs["PBSH"] = _clamp(str_ - 5, 40, 90)
        elif pos in OL_POSITIONS:
            attrs["PPBK"] = _clamp(str_ + 2, 50, 99)
            attrs["PRBK"] = _clamp(str_ + 2, 50, 99)
            attrs["PPBS"] = _clamp(str_, 50, 99)
            attrs["PRBS"] = _clamp(str_, 50, 99)
            attrs["PPBF"] = _clamp(str_ - 3, 45, 95)
            attrs["PBFW"] = _clamp(str_ - 3, 45, 95)
            attrs["PIBL"] = _clamp(str_ - 5, 45, 90)
            attrs["PDIS"] = _clamp(awr - 5, 40, 90)
        elif pos in DL_POSITIONS:
            attrs["PBSH"] = _clamp(str_ + 2, 50, 99)
            attrs["PTAK"] = _clamp(prod_rating + 5, 40, 95)
            attrs["PHIT"] = _clamp(str_ - 2, 45, 95)
            attrs["PFMV"] = _clamp(str_ - 8, 40, 90)
            attrs["PPMV"] = _clamp(str_ - 2, 45, 95)
            attrs["PSMV"] = _clamp(str_ - 10, 40, 85)
            attrs["PPRS"] = _clamp(awr, 45, 95)
        elif pos in LB_POSITIONS:
            attrs["PTAK"] = _clamp(prod_rating + 5, 40, 95)
            attrs["PHIT"] = _clamp(str_ - 2, 45, 95)
            attrs["PBSH"] = _clamp(str_ - 8, 40, 90)
            attrs["PPRS"] = _clamp(awr, 45, 95)
            attrs["PMCV"] = _clamp(awr - 5, 40, 90)
            attrs["PZCV"] = _clamp(awr - 3, 40, 90)
        elif pos in DB_POSITIONS:
            attrs["PMCV"] = _clamp(prod_rating + 5, 40, 99)
            attrs["PZCV"] = _clamp(prod_rating + 3, 40, 99)
            attrs["PPRS"] = _clamp(awr, 45, 95)
            attrs["PTAK"] = _clamp(prod_rating - 10, 40, 85)
            attrs["PHIT"] = _clamp(str_ - 5, 40, 85)
        elif pos in (19,):  # K
            attrs["PKPR"] = _clamp(70 + (prod_rating - 50) * 0.4, 40, 99)
            attrs["PKAC"] = _clamp(prod_rating + 5, 40, 99)
        elif pos in (20,):  # P
            attrs["PKPR"] = _clamp(70 + (prod_rating - 50) * 0.4, 40, 99)
            attrs["PKAC"] = _clamp(prod_rating, 40, 95)

        # OVR
        weights = OVR_WEIGHTS.get(pos, DEFAULT_OVR_WEIGHTS)
        num = sum(attrs.get(a, 50) * w for a, w in weights.items())
        den = sum(weights.values()) or 1
        ovr = num / den
        attrs["POVR"] = _clamp(ovr, 40, 99)

        # confidence tag
        tags = {"measured": prod_rating > 0 and (p.get("experience", 0) or 0) >= 1,
                "prior": False, "projected": False}
        if (p.get("experience", 0) or 0) < 1:
            tags["projected"] = True
        elif (p.get("_stats", {}) and len(p["_stats"]) < 3):
            tags["prior"] = True
        else:
            tags["measured"] = True
        p["_confidence"] = "measured" if tags["measured"] else ("prior" if tags["prior"] else "projected")
        p["_attrs"] = attrs
        results.append((p, attrs))
    return results
