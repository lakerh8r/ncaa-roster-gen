"""Write a rated roster into an EA TDBFile (in place)."""
from roster_gen.db.conferences import get_conference_id, prestige_for
from roster_gen.eadb import TDBFile

# Body definition (0-15, body type) and size (0-31, proportions) fields
BODY_DEF_FIELDS = ["BSAA", "BSBA", "BSCA", "BSFA", "BSGA", "BSPA",
                   "BSSA", "BSTA", "BSWA", "PHCL", "PLEL", "PREL",
                   "PLTH", "PRTH", "PLFB", "PRFB", "PLCB", "PRCB",
                   "PLBB", "PRBB", "PLKL", "PSPL", "PLSL", "PLKN",
                   "PRKN", "PLKR", "PRKR", "PLTW", "PLHW", "PLSO",
                   "LSLR", "LSRR"]
# Actually, let's just grab all BS* and PL*/PR* fields dynamically

BODY_SIZE_FIELDS = ["BSAT", "BSBT", "BSCT", "BSFT", "BSGT", "BSPT",
                    "BSST", "BSTT", "BSWT", "PLHA", "PRHA"]

FACE_FIELDS = ["PGHE", "PUHE", "PHCL"]


_body_index = None
_body_index_db = None


def _build_body_index(base_db):
    global _body_index, _body_index_db
    if base_db is _body_index_db and _body_index is not None:
        return _body_index
    _body_index_db = base_db
    if base_db is None:
        _body_index = None
        return None
    base_play = base_db.table("PLAY")
    idx = {}
    for i in range(base_play.current_records):
        r = base_play.record(i)
        pos = base_play.get_int(r, "PPOS")
        bw = base_play.get_int(r, "PWGT") + 160
        idx.setdefault(pos, []).append((bw, i))
    for pos in idx:
        idx[pos].sort(key=lambda x: x[0])
    _body_index = idx
    return idx


def _find_closest_body(base_db, pos, weight):
    """Find the base player (same position) with closest weight; return their body/face fields."""
    idx = _build_body_index(base_db)
    if idx is None or pos not in idx:
        return None
    entries = idx[pos]
    import bisect
    weights = [e[0] for e in entries]
    i = bisect.bisect_left(weights, weight)
    candidates = []
    if i > 0:
        candidates.append(entries[i - 1])
    if i < len(entries):
        candidates.append(entries[i])
    if not candidates:
        return None
    best_entry = min(candidates, key=lambda e: abs(e[0] - weight))
    base_play = base_db.table("PLAY")
    best_rec = base_play.record(best_entry[1])
    result = {}
    for f in base_play.fields:
        if f.is_string:
            continue
        if f.name.startswith("BS") or f.name.startswith("PL") or f.name.startswith("PR") or f.name in ("PGHE", "PUHE", "PHCL", "PHIT"):
            try:
                result[f.name] = base_play.get_int(best_rec, f.name)
            except Exception:
                pass
    return result


def _set_player_row(t, rec, p, attrs, base_db=None):
    t.set_str(rec, "PFNA", (p.get("first") or "")[:11])
    t.set_str(rec, "PLNA", (p.get("last") or "")[:13])
    t.set_int(rec, "PWGT", (p.get("weight", 200) - 160))
    t.set_int(rec, "TGID", p["team"])
    t.set_int(rec, "PPOS", p["pos"])
    t.set_int(rec, "PYEA", p.get("year", 1))
    t.set_int(rec, "PRSD", 1 if p.get("redshirt") else 0)
    t.set_int(rec, "PHGT", p.get("height", 72))
    t.set_int(rec, "PJEN", p.get("jersey", 0) or 0)
    for k, v in (attrs or {}).items():
        try:
            t.set_int(rec, k, int(v))
        except Exception:
            pass
    # Fix body type and skin tone: copy from closest base player by position+weight
    body = _find_closest_body(base_db, p["pos"], p.get("weight", 200))
    if body:
        for f, v in body.items():
            try:
                t.set_int(rec, f, v)
            except Exception:
                pass
    else:
        # fallback: reset body/face fields to 0 (game default)
        for f in t.fields:
            if (not f.is_string and
                    (f.name.startswith("BS") or f.name.startswith("PL") or
                     f.name.startswith("PR") or f.name in ("PGHE", "PUHE", "PHCL"))):
                try:
                    t.set_int(rec, f.name, 0)
                except Exception:
                    pass
    pgid = t.get_int(rec, "PGID")
    t.set_int(rec, "POID", pgid)


def write_roster(db, team_to_players, base_db=None, realignment=False, rankings=None, log=print):
    play = db.table("PLAY")
    rows_by_team = {}
    for i in range(play.current_records):
        r = play.record(i)
        tg = play.get_int(r, "TGID")
        rows_by_team.setdefault(tg, []).append(i)

    total_teams = len(team_to_players)
    for ti, (tgid, players) in enumerate(team_to_players.items()):
        slots = rows_by_team.get(tgid, [])
        if not players:
            # No data for this team (ESPN had no roster). Keep the base rows
            # instead of replacing 68 real players with "Walk On" and 00 jerseys.
            if (ti + 1) % 10 == 0 or ti == total_teams - 1:
                log(f"    Writing players... ({ti + 1}/{total_teams} teams)")
            continue
        used = {int(p.get("jersey") or 0) for p in players}
        spare = (n for n in range(1, 100) if n not in used)
        for slot_idx, row_i in enumerate(slots):
            rec = play.record(row_i)
            if slot_idx < len(players):
                p = players[slot_idx]
                p["team"] = tgid
                _set_player_row(play, rec, p, p.get("_attrs", {}), base_db=base_db)
            else:
                _set_player_row(play, rec, {
                    "first": "Walk", "last": "On", "pos": 1, "year": 1,
                    "height": 72, "weight": 190, "jersey": next(spare, 0),
                    "team": tgid,
                }, {"POVR": 45, "PSPD": 60, "PSTR": 55, "PAWR": 45}, base_db=base_db)
        if (ti + 1) % 10 == 0 or ti == total_teams - 1:
            log(f"    Writing players... ({ti + 1}/{total_teams} teams)")

    dcht = db.table("DCHT")
    matched_tgids = {tgid for tgid, players in team_to_players.items() if players}
    base_dcht_rows = []
    if base_db is not None:
        base_dcht = base_db.table("DCHT")
        for i in range(base_dcht.current_records):
            r = base_dcht.record(i)
            tg = base_dcht.get_int(r, "TGID")
            if tg not in matched_tgids:
                base_dcht_rows.append((
                    base_dcht.get_int(r, "PGID"),
                    tg,
                    base_dcht.get_int(r, "PPOS"),
                    base_dcht.get_int(r, "ddep"),
                ))
    new_rows = []
    for tgid, players in team_to_players.items():
        by_pos = {}
        for p in players:
            by_pos.setdefault(p["pos"], []).append(p)
        for pos, ps in by_pos.items():
            for depth, p in enumerate(ps):
                pgid = p.get("_pgid")
                if pgid is None:
                    continue
                new_rows.append((pgid, tgid, pos, depth))
    all_rows = base_dcht_rows + new_rows

    needed = len(all_rows)
    if needed > dcht.max_records:
        dcht.max_records = needed + 500

    dcht.current_records = 0
    for (pgid, tgid, pos, depth) in all_rows:
        rec = dcht.record(dcht.current_records)
        dcht.set_int(rec, "PGID", pgid)
        dcht.set_int(rec, "TGID", tgid)
        dcht.set_int(rec, "PPOS", pos)
        dcht.set_int(rec, "ddep", depth)
        dcht.current_records += 1

    team_tbl = db.table("TEAM")
    for i in range(team_tbl.row_count()):
        rec = team_tbl.record(i)
        tgid = team_tbl.get_int(rec, "TGID")
        ps = team_to_players.get(tgid, [])
        if not ps:
            continue
        ranked = sorted(ps, key=lambda p: p.get("_attrs", {}).get("POVR", 0), reverse=True)
        off = [p for p in ranked if p["pos"] in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)]
        deff = [p for p in ranked if p["pos"] not in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)]
        picks = []
        if off:
            picks.append(off[0])
        if deff:
            picks.append(deff[0])
        for p in ranked:
            if len(picks) >= 3:
                break
            if p not in picks:
                picks.append(p)
        while len(picks) < 3 and ps:
            picks.append(ps[0])
        ids = [p.get("_pgid", 0) for p in picks[:3]]
        while len(ids) < 3:
            ids.append(0)
        team_tbl.set_int(rec, "TSI1", ids[0])
        team_tbl.set_int(rec, "TMPI", ids[1] if len(ids) > 1 else 0)
        team_tbl.set_int(rec, "TPIO", ids[2] if len(ids) > 2 else 0)
        team_tbl.set_int(rec, "TSI2", 0xFFFF)

        ovrs = [p.get("_attrs", {}).get("POVR", 70) for p in ps]
        team_tbl.set_int(rec, "TROV", int(round(sum(ovrs) / len(ovrs))) if ovrs else 70)
        off_ovrs = [p.get("_attrs", {}).get("POVR", 70) for p in ps if p["pos"] in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)]
        def_ovrs = [p.get("_attrs", {}).get("POVR", 70) for p in ps if p["pos"] not in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)]
        team_tbl.set_int(rec, "TROF", int(round(sum(off_ovrs) / len(off_ovrs))) if off_ovrs else 70)
        team_tbl.set_int(rec, "TDRR", int(round(sum(def_ovrs) / len(def_ovrs))) if def_ovrs else 70)
        team_tbl.set_int(rec, "TRST", 70)

    # Phase A realignment: update conference, division, prestige
    if realignment:
        from roster_gen.db.conferences import get_conference_id
        for i in range(team_tbl.row_count()):
            rec = team_tbl.record(i)
            name = team_tbl.get_str(rec, "TDNA")
            cg = get_conference_id(name)
            if cg is not None:
                team_tbl.set_int(rec, "CGID", cg)

    # Top 25 rankings (AP + Coaches)
    if rankings:
        for i in range(team_tbl.row_count()):
            rec = team_tbl.record(i)
            name = team_tbl.get_str(rec, "TDNA")
            if name in rankings:
                ap_rank, coaches_rank = rankings[name]
                team_tbl.set_int(rec, "TMRK", ap_rank)
                team_tbl.set_int(rec, "TCRK", coaches_rank)