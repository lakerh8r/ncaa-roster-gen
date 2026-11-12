"""Helpers for reading/writing NCAA 14 roster data from a TDBFile."""
from roster_gen.eadb import TDBFile


def teams(db):
    t = db.table("TEAM")
    out = []
    for i in range(t.row_count()):
        r = t.record(i)
        out.append({
            "row": i,
            "tgid": t.get_int(r, "TGID"),
            "name": t.get_str(r, "TDNA"),
            "long": t.get_str(r, "TLNA"),
            "mascot": t.get_str(r, "TMNA"),
            "short": t.get_str(r, "TSNA"),
            "conf": t.get_int(r, "CGID"),
            "div": t.get_int(r, "DGID"),
            "type": t.get_int(r, "TTYP"),
        })
    return out


def players(db, tgid=None):
    t = db.table("PLAY")
    out = []
    for i in range(t.current_records):
        r = t.record(i)
        row_tgid = t.get_int(r, "TGID")
        if tgid is not None and row_tgid != tgid:
            continue
        out.append({
            "row": i,
            "pgid": t.get_int(r, "PGID"),
            "first": t.get_str(r, "PFNA"),
            "last": t.get_str(r, "PLNA"),
            "pos": t.get_int(r, "PPOS"),
            "year": t.get_int(r, "PYEA"),
            "redshirt": t.get_int(r, "PRSD"),
            "height": t.get_int(r, "PHGT"),
            "weight": t.get_int(r, "PWGT") + 160,
            "jersey": t.get_int(r, "PJEN"),
            "ovr": t.get_int(r, "POVR"),
            "spd": t.get_int(r, "PSPD"),
            "team": row_tgid,
        })
    return out


POSITIONS = {
    0: "QB", 1: "HB", 2: "FB", 3: "WR", 4: "TE",
    5: "LT", 6: "LG", 7: "C", 8: "RG", 9: "RT",
    10: "LE", 11: "RE", 12: "DT", 13: "LLB", 14: "MLB",
    15: "RLB", 16: "CB", 17: "FS", 18: "SS", 19: "K", 20: "P",
}


def position_name(code):
    return POSITIONS.get(code, f"?{code}")