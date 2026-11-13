"""End-to-end pipeline: scrape -> rate -> write save -> report."""
import os
import json
import time
from datetime import datetime

from roster_gen.ps3.save import decrypt_save, encrypt_save
from roster_gen.eadb import TDBFile
from roster_gen.db.roster import teams, players
from roster_gen.db.writer import write_roster
from roster_gen.sources.espn import espn_team_roster, espn_player_stats, map_position
from roster_gen.sources.team_map import build_team_map
from roster_gen.ratings.engine import rate_players
from concurrent.futures import ThreadPoolExecutor, as_completed


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def _dur(seconds):
    """Human friendly duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(seconds, 60)
    return f"{int(minutes)}m {secs:.0f}s"


def _season_str(y):
    return f"{y}-{str(y + 1)[-2:]}"


def _class_to_year(cls, exp):
    c = (cls or "").upper()
    if c.startswith("FR"):
        return 0
    if c.startswith("SO"):
        return 1
    if c.startswith("JR"):
        return 2
    if c.startswith("SR"):
        return 3
    if c.startswith("GR") or "5" in c or "6" in c or (exp or 0) >= 4:
        return 4
    return min(4, exp or 0)


def run(year, base_dir, out_dir=None, log=print, rename=True, realignment=False,
        rankings=True, workers=10, skip_stats=False):
    season = year
    prior = year - 1
    if out_dir is None:
        out_dir = "/home/lakerh8r/Downloads/NCAA14RosterPack"
    os.makedirs(out_dir, exist_ok=True)
    save_name = f"BLUS31159-ROSTER-{season}" if rename else "BLUS31159-ROSTER-JHASLEY10"
    save_dir = os.path.join(out_dir, "PS3", "SAVEDATA", save_name)
    os.makedirs(save_dir, exist_ok=True)

    _t0 = time.time()
    log_lines = []
    _orig_log = log

    def _log(msg=""):
        line = f"[{_ts()}] {msg}" if msg else ""
        log_lines.append(line)
        _orig_log(line)

    log = _log

    _step_t = {"last": _t0}
    step_times = []

    def _mark(label):
        now = time.time()
        seconds = now - _step_t["last"]
        step_times.append((label, seconds))
        log(f"  --> {label} completed in {_dur(seconds)}")
        _step_t["last"] = now

    log("[1/6] Decrypting base save...")
    work = os.path.join("/tmp/opencode/scratchpad", f"run_{season}")
    os.makedirs(work, exist_ok=True)
    db_path, _ = decrypt_save(base_dir, work)
    db = TDBFile(open(db_path, "rb").read())
    assert db.verify() == [], "base DB failed verification"

    base_teams = [t for t in teams(db) if t["type"] == 0]
    ncaa_names = [t["name"] for t in base_teams]
    log(f"      {len(base_teams)} FBS teams")
    _mark("Step 1: decrypt base save")

    log("[2/6] Mapping teams to ESPN...")
    tmap = build_team_map(ncaa_names)
    matched = sum(1 for v in tmap.values() if v)
    log(f"      matched {matched}/{len(ncaa_names)}")
    _mark("Step 2: map teams")

    # base slot counts + pgids
    base_counts = {}
    base_pgids = {}
    for t in base_teams:
        ps = players_list(db, t["tgid"])
        base_counts[t["tgid"]] = len(ps)
        base_pgids[t["tgid"]] = [p["pgid"] for p in ps]

    log("[3/6] Scraping rosters...")
    log(f"  Fetching {len(base_teams)} rosters in parallel ({workers} workers)...")
    roster_cache = {}
    teams_with_espn = [(t, tmap.get(t["name"])) for t in base_teams if tmap.get(t["name"])]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_team = {executor.submit(espn_team_roster, eid): (t, eid) for t, eid in teams_with_espn}
        for future in as_completed(future_to_team):
            t, eid = future_to_team[future]
            try:
                roster_cache[eid] = future.result()
            except Exception as e:
                log(f"        roster fetch failed for {t['name']}: {e}")
                roster_cache[eid] = []

    team_to_players = {}
    all_players = []
    BROAD = {"OL": [5, 6, 7, 8, 9], "DL": [10, 11, 12], "LB": [13, 14, 15],
             "DB": [16, 17, 18], "EDGE": [10, 11]}
    SPECIFIC_MAP = {
        "QB": 0, "RB": 1, "HB": 1, "FB": 2, "WR": 3, "TE": 4,
        "OT": 5, "LT": 5, "OG": 6, "LG": 6, "G": 6, "C": 7, "RG": 8, "RT": 9,
        "DE": 10, "LE": 10, "RE": 11, "DT": 12, "NT": 12,
        "OLB": 13, "ILB": 14, "MLB": 14, "LLB": 13, "RLB": 15,
        "CB": 16, "S": 17, "FS": 17, "SS": 18,
        "K": 19, "PK": 19, "P": 20, "LS": 4,
    }

    JERSEY_RANGES = {
        0: (1, 19), 1: (20, 49), 2: (30, 49), 3: (80, 89), 4: (40, 49),
        5: (50, 79), 6: (50, 79), 7: (50, 79), 8: (50, 79), 9: (50, 79),
        10: (90, 99), 11: (90, 99), 12: (90, 99),
        13: (40, 59), 14: (40, 59), 15: (40, 59),
        16: (20, 49), 17: (20, 49), 18: (20, 49),
        19: (1, 19), 20: (1, 19),
    }

    for ti, t in enumerate(base_teams):
        tg = t["tgid"]
        espn_id = tmap.get(t["name"])
        slots = base_counts[tg]
        log(f"      [{ti+1}/{len(base_teams)}] {t['name']} (slots={slots}) espn={espn_id}")
        if not espn_id:
            team_to_players[tg] = []
            continue
        roster = roster_cache.get(espn_id, [])
        if not roster:
            team_to_players[tg] = []
            continue

        base_pos_counts = {}
        for bp in players_list(db, tg):
            base_pos_counts[bp["pos"]] = base_pos_counts.get(bp["pos"], 0) + 1

        specific_players = []
        broad_players = []
        for rp in roster:
            espn_pos = rp["pos"]
            if espn_pos in BROAD:
                broad_players.append(rp)
            else:
                code = SPECIFIC_MAP.get(espn_pos)
                if code is None and espn_pos == "EDGE":
                    code = 10 if (rp.get("weight") or 0) >= 250 else 11
                if code is None:
                    code = map_position(espn_pos, rp.get("weight"))
                if code is None:
                    continue
                specific_players.append((rp, code))

        cand = []
        for rp, code in specific_players:
            cand.append({
                "first": rp["first"], "last": rp["last"], "pos": code,
                "year": _class_to_year(rp.get("class"), rp.get("experience", 0)),
                "redshirt": 1 if (rp.get("class") or "").startswith("R") else 0,
                "height": int(rp["height"] or 72), "weight": int(rp["weight"] or 200),
                "jersey": int(rp["jersey"]) if rp.get("jersey") else 0,
                "experience": rp.get("experience", 0) or 0,
                "espn_id": rp["espn_id"], "_class": rp.get("class", ""),
                "_status": rp.get("status", "active"),
                "slug": rp.get("slug", ""),
            })

        cur_counts = {}
        for c in cand:
            cur_counts[c["pos"]] = cur_counts.get(c["pos"], 0) + 1

        for rp in broad_players:
            espn_pos = rp["pos"]
            targets = BROAD.get(espn_pos, [])
            if not targets:
                continue
            best_pos = None
            best_shortfall = -999
            for tp in targets:
                target = base_pos_counts.get(tp, 1)
                shortfall = target - cur_counts.get(tp, 0)
                if shortfall > best_shortfall:
                    best_shortfall = shortfall
                    best_pos = tp
            if best_pos is None:
                best_pos = targets[0]
            cur_counts[best_pos] = cur_counts.get(best_pos, 0) + 1
            cand.append({
                "first": rp["first"], "last": rp["last"], "pos": best_pos,
                "year": _class_to_year(rp.get("class"), rp.get("experience", 0)),
                "redshirt": 1 if (rp.get("class") or "").startswith("R") else 0,
                "height": int(rp["height"] or 72), "weight": int(rp["weight"] or 200),
                "jersey": int(rp["jersey"]) if rp.get("jersey") else 0,
                "experience": rp.get("experience", 0) or 0,
                "espn_id": rp["espn_id"], "_class": rp.get("class", ""),
                "_status": rp.get("status", "active"),
                "slug": rp.get("slug", ""),
            })

        # Filter graduated/inactive
        filtered = []
        sr_grads = [p for p in cand if ((p["_class"] or "").upper().startswith("SR") or
                    (p["_class"] or "").upper().startswith("GR") or
                    "5" in (p["_class"] or "") or "6" in (p["_class"] or ""))]
        stats_results = {}
        if sr_grads and not skip_stats:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(espn_player_stats, p["espn_id"], p.get("slug", "")): p for p in sr_grads}
                for future in as_completed(futures):
                    p = futures[future]
                    try:
                        stats_results[p["espn_id"]] = future.result()
                    except Exception:
                        stats_results[p["espn_id"]] = {}

        for p in cand:
            cls = (p["_class"] or "").upper()
            is_fr = cls.startswith("FR") or (p["experience"] or 0) == 0
            is_underclass = cls.startswith("SO") or cls.startswith("JR") or cls.startswith("FR")
            is_sr_grad = cls.startswith("SR") or cls.startswith("GR") or "5" in cls or "6" in cls
            st = {}
            if not skip_stats and is_sr_grad:
                st = stats_results.get(p["espn_id"], {})
            p["_stats_raw"] = st
            seasons = sorted([s for s in st.keys() if s.isdigit()], key=lambda x: int(x), reverse=True)
            has_current = str(season) in st
            has_prior = str(prior) in st
            has_recent = any(int(s) >= season - 2 for s in seasons if s.isdigit())
            espn_status = (p.get("_status") or "active").lower()
            is_inactive = espn_status in ("inactive", "out", "suspended")
            if is_inactive:
                keep = False
            elif is_fr:
                keep = True
            elif has_current:
                keep = True
            elif is_underclass:
                keep = True
            elif is_sr_grad and has_prior:
                keep = True
            elif is_sr_grad and has_recent:
                keep = True
            elif is_sr_grad and len(seasons) == 0:
                keep = True
            elif is_sr_grad and not has_recent:
                keep = False
            else:
                keep = True
            if keep:
                filtered.append(p)
            else:
                log(f"        filtered out (graduated/inactive): {p['first']} {p['last']} ({p['_class']})")
        cand = filtered

        def _depth_key(p):
            st = p.get("_stats_raw", {}) or {}
            def _num(v):
                try:
                    return float(str(v).replace(",", "")) if v is not None else 0
                except (ValueError, TypeError):
                    return 0
            touches = _num(st.get("receptions", 0)) + _num(st.get("rushingAttempts", 0)) + _num(st.get("completions", 0)) + _num(st.get("tackles", 0))
            jersey_priority = 0 if p.get("_had_jersey", False) else 1
            return (jersey_priority, -touches, -(p.get("experience", 0) or 0))

        # mark jersey status before assignment
        for p in cand:
            p["_had_jersey"] = (p.get("jersey", 0) or 0) > 0

        cand.sort(key=_depth_key)
        chosen = cand[:slots]

        # fetch stats for chosen (reuse cached)
        for p in chosen:
            st = p.get("_stats_raw", {})
            if not st and not skip_stats:
                try:
                    st = espn_player_stats(p["espn_id"], p.get("slug", ""))
                except Exception:
                    st = {}
            cur = st.get(str(season), {}) or st.get(str(season) + " Season", {}) or {}
            pri = st.get(str(prior), {}) or {}
            seasons = [s for s in st.keys() if s.lower() != "career"]
            if not cur and seasons:
                seasons_sorted = sorted(seasons, key=lambda x: int(x) if x.isdigit() else 0, reverse=True)
                cur = st.get(seasons_sorted[0], {}) if seasons_sorted else {}
                pri = st.get(seasons_sorted[1], {}) if len(seasons_sorted) > 1 else {}
            p["stats"] = cur
            p["prior_stats"] = pri

        # assign jersey numbers
        used_numbers = set()
        for p in chosen:
            j = p.get("jersey", 0) or 0
            if j > 0:
                used_numbers.add(j)
        for p in chosen:
            j = p.get("jersey", 0) or 0
            if j == 0:
                lo, hi = JERSEY_RANGES.get(p["pos"], (1, 99))
                assigned = None
                for num in range(lo, hi + 1):
                    if num not in used_numbers:
                        assigned = num
                        break
                if assigned is None:
                    for num in range(1, 100):
                        if num not in used_numbers:
                            assigned = num
                            break
                if assigned is not None:
                    p["jersey"] = assigned
                    used_numbers.add(assigned)

        # walk-ons if short
        while len(chosen) < slots:
            p = {"first": "Walk", "last": "On", "pos": 1, "year": 1, "redshirt": 0,
                 "height": 72, "weight": 190, "jersey": 0, "experience": 0,
                 "stats": {}, "prior_stats": {}, "_pgid": None, "_had_jersey": False,
                 "_class": "", "_status": "active", "slug": "", "espn_id": None}
            chosen.append(p)

        # assign pgids from base slots
        pgids = base_pgids[tg]
        for i, p in enumerate(chosen):
            if i < len(pgids):
                p["_pgid"] = pgids[i]
            else:
                p["_pgid"] = pgids[-1] if pgids else 0
        # assign jersey to walk-ons
        for p in chosen:
            if (p.get("jersey", 0) or 0) == 0:
                for num in range(20, 100):
                    if num not in used_numbers:
                        p["jersey"] = num
                        used_numbers.add(num)
                        break
        team_to_players[tg] = chosen
        all_players.extend(chosen)

    _mark("Step 3: scrape rosters")

    log(f"[4/6] Rating {len(all_players)} players...")
    has_current_stats = any(p.get("stats") for p in all_players)
    if not has_current_stats:
        log(f"  WARNING: No {season} stats found. Using {prior} stats only (100% prior season).")
        log(f"  This is normal for pre-season runs.")
        current_weight = 0.0
    else:
        current_weight = 0.6
    freshmen_count = sum(1 for p in all_players if (p.get("_class") or "").upper().startswith("FR") or (p.get("experience") or 0) == 0)
    if season > 2026 and freshmen_count == 0:
        log(f"  WARNING: No freshmen found. ESPN roster may not be updated for {season} yet.")
    rate_players(all_players, current_weight=current_weight)
    _mark("Step 4: rate players")

    log("[5/6] Writing DB...")
    base_db = TDBFile(open(db_path, "rb").read())
    ranking_map = None
    if rankings:
        log("  Fetching AP Top 25 + Coaches Poll...")
        from roster_gen.sources.rankings import build_ranking_map
        ncaa_names = [t["name"] for t in teams(db) if t["type"] == 0]
        tmap2 = build_team_map(ncaa_names)
        ranking_map = build_ranking_map(tmap2)
        ranked = sum(1 for v in ranking_map.values() if v[0] > 0)
        log(f"  Ranked teams: {ranked}")
        _mark("Step 5a: fetch Top 25 polls")
    log(f"  Writing {len(all_players)} players and depth charts...")
    write_roster(db, team_to_players, base_db=base_db, realignment=realignment,
                 rankings=ranking_map, log=log)
    log("  Writing team ratings and conference data...")
    _mark("Step 5: write DB")

    log(f"[6/6] Encrypting save -> {out_dir}")
    new_db = db.build()
    CONTAINER_SIZE = 1433600
    if len(new_db) < CONTAINER_SIZE:
        new_db = new_db + b"\x00" * (CONTAINER_SIZE - len(new_db))
    with open(os.path.join(work, "USR-DATA"), "wb") as f:
        f.write(new_db)
    from roster_gen.ps3.save import encrypt_save
    encrypt_save(work, save_dir, base_dir, sfo_source_dir=None, account_id=None)
    _mark("Step 6: encrypt save")

    elapsed = time.time() - _t0
    log(f"Done. Output root: {out_dir}")
    log(f"Save folder: {save_dir}")
    log(f"Total time: {_dur(elapsed)}")
    log("")
    log("=== WHERE TO COPY ON YOUR PS3 ===")
    log("USB drive: copy the 'PS3' folder to the ROOT of your USB drive.")
    log("  Then on PS3: Game -> Save Data Utility (PS3) -> copy from USB to HDD.")
    log("FTP: upload 'BLUS31159-ROSTER-...' into /dev_hdd0/home/00000001/savedata/")
    log("  (skip the PS3/SAVEDATA wrapper for FTP)")
    log("Then launch NCAA Football 14.")

    # report + csv
    report_path = os.path.join(out_dir, "report.txt")
    conf = {}
    for p in all_players:
        conf[p.get("_confidence", "?")] = conf.get(p.get("_confidence", "?"), 0) + 1
    bar = "=" * 60
    with open(report_path, "w") as f:
        f.write("NCAA Football 14 Roster Generator - Run Log\n")
        f.write(bar + "\n")
        f.write(f"Season: {_season_str(season)}\n")
        f.write("Started: " + datetime.fromtimestamp(_t0).strftime("%Y-%m-%d %H:%M:%S") + "\n")
        f.write("Finished: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        f.write(bar + "\n\n")

        # full timestamped log
        for line in log_lines:
            f.write(line + "\n")

        # step timings
        f.write("\n" + bar + "\n")
        f.write("STEP TIMINGS\n")
        f.write("-" * 60 + "\n")
        for label, seconds in step_times:
            dots = "." * max(2, 38 - len(label))
            f.write(f"{label} {dots} {_dur(seconds)}\n")
        f.write(f"{'TOTAL':<38} {_dur(elapsed)}\n")
        f.write(bar + "\n\n")

        # summary
        f.write("SUMMARY\n")
        f.write("-" * 60 + "\n")
        f.write(f"Teams: {len(base_teams)}\n")
        f.write(f"Players rated: {len(all_players)}\n")
        f.write(f"Matched to ESPN: {matched}/{len(ncaa_names)}\n")
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
    return out_dir


# Need players function (import from roster module)
from roster_gen.db.roster import players as players_list