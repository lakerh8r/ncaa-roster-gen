"""Write a rated roster into an EA TDBFile (in place)."""
from roster_gen.db.roster import POSITIONS
from roster_gen.eadb import TDBFile


def _set_player_row(t, rec, p, attrs):
    """Fill a PLAY record with player identity + attributes."""
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
    # POID = PGID (keep persistent id)
    pgid = t.get_int(rec, "PGID")
    t.set_int(rec, "POID", pgid)


def write_roster(db, team_to_players):
    """team_to_players: {tgid: [player_dict_with_'attrs']}.

    Reuses existing PLAY rows per team (preserving count). Regenerates DCHT.
    """
    play = db.table("PLAY")
    # group existing rows by team
    rows_by_team = {}
    for i in range(play.current_records):
        r = play.record(i)
        tg = play.get_int(r, "TGID")
        rows_by_team.setdefault(tg, []).append(i)

    # fill each team's slots
    for tgid, players in team_to_players.items():
        slots = rows_by_team.get(tgid, [])
        # sort players by priority: position then production
        # fill slots
        for slot_idx, row_i in enumerate(slots):
            rec = play.record(row_i)
            if slot_idx < len(players):
                p = players[slot_idx]
                p["team"] = tgid
                _set_player_row(play, rec, p, p.get("_attrs", {}))
            else:
                # walk-on placeholder
                _set_player_row(play, rec, {
                    "first": "Walk", "last": "On", "pos": 1, "year": 1,
                    "height": 72, "weight": 190, "jersey": 0, "team": tgid,
                }, {"POVR": 45, "PSPD": 60, "PSTR": 55, "PAWR": 45})

    # regenerate DCHT
    dcht = db.table("DCHT")
    # collect new depth chart rows: for each team, for each position, players in order
    new_rows = []
    for tgid, players in team_to_players.items():
        # group by position
        by_pos = {}
        for p in players:
            by_pos.setdefault(p["pos"], []).append(p)
        for pos, ps in by_pos.items():
            for depth, p in enumerate(ps):
                # find the PLAY row's PGID for this player
                # (we reused slots; need pgid). We'll store pgid in player dict.
                pgid = p.get("_pgid")
                if pgid is None:
                    continue
                new_rows.append((pgid, tgid, pos, depth))

    # ensure capacity
    needed = len(new_rows)
    if needed > dcht.max_records:
        dcht.max_records = needed + 100

    # reset current_records and append
    dcht.current_records = 0
    for (pgid, tgid, pos, depth) in new_rows:
        rec = dcht.record(dcht.current_records)
        dcht.set_int(rec, "PGID", pgid)
        dcht.set_int(rec, "TGID", tgid)
        dcht.set_int(rec, "PPOS", pos)
        dcht.set_int(rec, "ddep", depth)
        dcht.current_records += 1

    # impact players: top 3 by OVR per team, at least 1 off + 1 def
    team_tbl = db.table("TEAM")
    for i in range(team_tbl.row_count()):
        rec = team_tbl.record(i)
        tgid = team_tbl.get_int(rec, "TGID")
        ps = team_to_players.get(tgid, [])
        if not ps:
            continue
        # pick top OVR
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
        # pad with first player if needed
        while len(picks) < 3 and ps:
            picks.append(ps[0])
        ids = [p.get("_pgid", 0) for p in picks[:3]]
        while len(ids) < 3:
            ids.append(0)
        team_tbl.set_int(rec, "TSI1", ids[0])
        team_tbl.set_int(rec, "TMPI", ids[1] if len(ids) > 1 else 0)
        team_tbl.set_int(rec, "TPIO", ids[2] if len(ids) > 2 else 0)
        team_tbl.set_int(rec, "TSI2", 0xFFFF)

    # team ratings
    for i in range(team_tbl.row_count()):
        rec = team_tbl.record(i)
        tgid = team_tbl.get_int(rec, "TGID")
        ps = team_to_players.get(tgid, [])
        if not ps:
            continue
        ovrs = [p.get("_attrs", {}).get("POVR", 70) for p in ps]
        team_tbl.set_int(rec, "TROV", int(round(sum(ovrs) / len(ovrs))) if ovrs else 70)
        # offense rating = avg of offensive players
        off_ovrs = [p.get("_attrs", {}).get("POVR", 70) for p in ps if p["pos"] in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)]
        def_ovrs = [p.get("_attrs", {}).get("POVR", 70) for p in ps if p["pos"] not in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)]
        team_tbl.set_int(rec, "TROF", int(round(sum(off_ovrs) / len(off_ovrs))) if off_ovrs else 70)
        team_tbl.set_int(rec, "TDRR", int(round(sum(def_ovrs) / len(def_ovrs))) if def_ovrs else 70)
        team_tbl.set_int(rec, "TRST", 70)