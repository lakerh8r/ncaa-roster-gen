"""End-to-end pipeline: scrape -> rate -> write save -> report."""
import os
import json
import time
from roster_gen.ps3.save import decrypt_save, encrypt_save
from roster_gen.eadb import TDBFile
from roster_gen.db.roster import teams, players, POSITIONS, position_name
from roster_gen.db.writer import write_roster
from roster_gen.sources.espn import espn_team_roster, espn_player_stats, map_position
from roster_gen.sources.team_map import build_team_map
from roster_gen.ratings.engine import rate_players


def _season_str(y):
    return f"{y}-{str(y + 1)[-2:]}"


def run(year, base_dir, out_dir=None, log=print):
    season = year
    prior = year - 1
    if out_dir is None:
        out_dir = os.path.join(os.path.dirname(base_dir), f"BLUS31159-ROSTER-{season}")

    log(f"[1/6] Decrypting base save...")
    work = os.path.join("/tmp/opencode/scratchpad", f"run_{season}")
    os.makedirs(work, exist_ok=True)
    db_path, _ = decrypt_save(base_dir, work)
    db = TDBFile(open(db_path, "rb").read())
    assert db.verify() == [], "base DB failed verification"

    base_teams = [t for t in teams(db) if t["type"] == 0]
    ncaa_names = [t["name"] for t in base_teams]
    log(f"      {len(base_teams)} FBS teams")

    log(f"[2/6] Mapping teams to ESPN...")
    tmap = build_team_map(ncaa_names)
    matched = sum(1 for v in tmap.values() if v)
    log(f"      matched {matched}/{len(ncaa_names)}")

    log(f"[3/6] Scraping rosters...")
    # base slot counts per team
    base_counts = {}
    base_pgids = {}
    for t in base_teams:
        ps = players(db, t["tgid"])
        base_counts[t["tgid"]] = len(ps)
        base_pgids[t["tgid"]] = [p["pgid"] for p in ps]

    team_to_players = {}
    all_players = []
    for ti, t in enumerate(base_teams):
        tg = t["tgid"]
        espn_id = tmap.get(t["name"])
        slots = base_counts[tg]
        log(f"      [{ti+1}/{len(base_teams)}] {t['name']} (slots={slots}) espn={espn_id}")
        if not espn_id:
            # leave base players untouched
            team_to_players[tg] = []
            continue
        try:
            roster = espn_team_roster(espn_id)
        except Exception as e:
            log(f"        roster fetch failed: {e}")
            team_to_players[tg] = []
            continue
        # map to NCAA positions, sort by experience then name
        cand = []
        for rp in roster:
            code = map_position(rp["pos"], rp.get("weight"))
            if code is None:
                continue
            cand.append({
                "first": rp["first"],
                "last": rp["last"],
                "pos": code,
                "year": _class_to_year(rp.get("class"), rp.get("experience", 0)),
                "redshirt": 1 if (rp.get("class") or "").startswith("R") else 0,
                "height": int(rp["height"] or 72),
                "weight": int(rp["weight"] or 200),
                "jersey": int(rp["jersey"]) if rp.get("jersey") else 0,
                "experience": rp.get("experience", 0) or 0,
                "espn_id": rp["espn_id"],
            })
        # priority sort: experienced first, then by position need
        cand.sort(key=lambda x: (-x["experience"], x["pos"]))
        # take top `slots`
        chosen = cand[:slots]
        # fetch stats for each
        for p in chosen:
            try:
                st = espn_player_stats(p["espn_id"])
            except Exception as e:
                st = {}
            # st: {season: {stats}}; current and prior
            cur = st.get(str(season), {}) or st.get(str(season) + " Season", {}) or {}
            pri = st.get(str(prior), {}) or {}
            # if ESPN seasons keyed differently, try last two non-career
            seasons = [s for s in st.keys() if s.lower() != "career"]
            if not cur and seasons:
                # pick the most recent
                seasons_sorted = sorted(seasons, key=lambda x: int(x) if x.isdigit() else 0, reverse=True)
                cur = st.get(seasons_sorted[0], {}) if seasons_sorted else {}
                pri = st.get(seasons_sorted[1], {}) if len(seasons_sorted) > 1 else {}
            p["stats"] = cur
            p["prior_stats"] = pri
        # assign pgids from base slots
        pgids = base_pgids[tg]
        for i, p in enumerate(chosen):
            if i < len(pgids):
                p["_pgid"] = pgids[i]
            else:
                p["_pgid"] = pgids[-1] if pgids else 0
        # walk-ons if short
        while len(chosen) < slots:
            p = {"first": "Walk", "last": "On", "pos": 1, "year": 1, "redshirt": 0,
                 "height": 72, "weight": 190, "jersey": 0, "experience": 0,
                 "stats": {}, "prior_stats": {}, "_pgid": pgids[len(chosen)] if len(chosen) < len(pgids) else 0}
            chosen.append(p)
        team_to_players[tg] = chosen
        all_players.extend(chosen)

    log(f"[4/6] Rating {len(all_players)} players...")
    rate_players(all_players)

    log(f"[5/6] Writing DB...")
    write_roster(db, team_to_players)
    # save db
    new_db = db.build()
    with open(os.path.join(work, "USR-DATA"), "wb") as f:
        f.write(new_db)

    log(f"[6/6] Encrypting save -> {out_dir}")
    encrypt_save(work, out_dir, base_dir)

    # report
    report_path = os.path.join(out_dir, "report.txt")
    with open(report_path, "w") as f:
        f.write(f"Season: {_season_str(season)}\n")
        f.write(f"Teams: {len(base_teams)}\n")
        f.write(f"Players rated: {len(all_players)}\n")
        f.write(f"Matched to ESPN: {matched}/{len(ncaa_names)}\n")
        conf = {}
        for p in all_players:
            conf[p.get("_confidence", "?")] = conf.get(p.get("_confidence", "?"), 0) + 1
        f.write(f"Confidence: {conf}\n")
        f.write("\nPer-team:\n")
        for t in base_teams:
            ps = team_to_players.get(t["tgid"], [])
            f.write(f"  {t['name']}: {len(ps)} players (espn={tmap.get(t['name'])})\n")
    import csv
    csv_path = os.path.join(out_dir, "roster.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["team", "first", "last", "pos", "ovr", "spd", "str", "awr", "conf"])
        for t in base_teams:
            for p in team_to_players.get(t["tgid"], []):
                a = p.get("_attrs", {})
                w.writerow([t["name"], p.get("first"), p.get("last"), p["pos"],
                            a.get("POVR"), a.get("PSPD"), a.get("PSTR"), a.get("PAWR"),
                            p.get("_confidence")])
    log(f"Done. Output: {out_dir}")
    return out_dir


def _class_to_year(cls, exp):
    # map ESPN class abbr to NCAA 14 year code (0=FR..3=SR, 4=5th)
    c = (cls or "").upper()
    if c.startswith("FR"):
        return 0
    if c.startswith("SO"):
        return 1
    if c.startswith("JR"):
        return 2
    if c.startswith("SR"):
        return 3
    if c.startswith("GR") or "5" in c or (exp or 0) >= 4:
        return 4
    return min(4, exp or 0)
