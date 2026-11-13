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


def run(year, base_dir, out_dir=None, log=print, rename=True, realignment=False, rankings=True, workers=10):
    season = year
    prior = year - 1
    if out_dir is None:
        out_dir = "/home/lakerh8r/Downloads/NCAA14RosterPack"
    os.makedirs(out_dir, exist_ok=True)
    if rename:
        save_name = f"BLUS31159-ROSTER-{season}"
    else:
        save_name = "BLUS31159-ROSTER-JHASLEY10"
    save_dir = os.path.join(out_dir, "PS3", "SAVEDATA", save_name)
    os.makedirs(save_dir, exist_ok=True)

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

    # Fetch all rosters in parallel
    log(f"  Fetching {len(base_teams)} rosters in parallel ({workers} workers)...")
    from concurrent.futures import ThreadPoolExecutor, as_completed
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
        # base position counts for this team (target distribution)
        base_ps = players(db, tg) if False else None
        # get base position counts from the base db
        base_pos_counts = {}
        for bp in players(db, tg):
            base_pos_counts[bp["pos"]] = base_pos_counts.get(bp["pos"], 0) + 1

        # separate specific vs broad positions
        BROAD = {"OL": [5,6,7,8,9], "DL": [10,11,12], "LB": [13,14,15], "DB": [16,17,18], "EDGE": [10,11]}
        SPECIFIC_MAP = {
            "QB":0,"RB":1,"HB":1,"FB":2,"WR":3,"TE":4,
            "OT":5,"LT":5,"OG":6,"LG":6,"G":6,"C":7,"RG":8,"RT":9,
            "DE":10,"LE":10,"RE":11,"DT":12,"NT":12,
            "LB":None,"OLB":13,"ILB":14,"MLB":14,"LLB":13,"RLB":15,
            "CB":16,"S":17,"FS":17,"SS":18,
            "K":19,"PK":19,"P":20,"LS":4,
        }

        # first pass: map specific positions
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

        # build candidate list with specific positions assigned
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
            })

        # distribute broad-label players to fill base position counts
        # current counts
        cur_counts = {}
        for c in cand:
            cur_counts[c["pos"]] = cur_counts.get(c["pos"], 0) + 1

        for rp in broad_players:
            espn_pos = rp["pos"]
            targets = BROAD.get(espn_pos, [])
            if not targets:
                continue
            # pick the target position with the largest shortfall vs base
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
            })
        # filter out graduated/inactive players:
        # keep if freshman, or has 2026 stats, or underclassman (So/Jr),
        # or senior/grad with 2025 stats (returning). Drop Sr/Gr with no recent stats.
        filtered = []
        # Parallel stats fetch for seniors/grads only
        sr_grads = [p for p in cand if ((p["_class"] or "").upper().startswith("SR") or
                    (p["_class"] or "").upper().startswith("GR") or
                    "5" in (p["_class"] or "") or "6" in (p["_class"] or ""))]
        stats_results = {}
        if sr_grads:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(espn_player_stats, p["espn_id"]): p for p in sr_grads}
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
            # Only fetch stats for seniors/grads (others are always kept)
            st = {}
            if is_sr_grad:
                st = stats_results.get(p["espn_id"], {})
            p["_stats_raw"] = st
            seasons = sorted([s for s in st.keys() if s.isdigit()], key=lambda x: int(x), reverse=True)
            has_current = str(season) in st
            has_prior = str(prior) in st
            has_recent = any(int(s) >= season - 2 for s in seasons if s.isdigit())
            espn_status = (p.get("_status") or "active").lower()
            is_inactive = espn_status in ("inactive", "out", "suspended")
            if is_inactive:
                keep = False  # ESPN says inactive
            elif is_fr:
                keep = True
            elif has_current:
                keep = True
            elif is_underclass:
                keep = True
            elif is_sr_grad and has_prior:
                keep = True  # returning senior/grad with prior year stats
            elif is_sr_grad and has_recent:
                keep = True  # senior with stats from 1-2 years ago (transfer)
            elif is_sr_grad and len(seasons) == 0:
                keep = True  # senior with no stats at all (new player, keep)
            elif is_sr_grad and not has_recent:
                keep = False  # graduated (last played 2+ years ago)
            else:
                keep = True  # default: keep unknowns
            if keep:
                filtered.append(p)
            else:
                log(f"        filtered out (graduated/inactive): {p['first']} {p['last']} ({p['_class']})")
        cand = filtered
        # priority sort: experienced first, then by position need
        cand.sort(key=lambda x: (-x["experience"], x["pos"]))
        # take top `slots`
        chosen = cand[:slots]
        # fetch stats for each (reuse cached from filter; only fetch if missing)
        for p in chosen:
            st = p.get("_stats_raw", {})
            if not st:
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
                seasons_sorted = sorted(seasons, key=lambda x: int(x) if x.isdigit() else 0, reverse=True)
                cur = st.get(seasons_sorted[0], {}) if seasons_sorted else {}
                pri = st.get(seasons_sorted[1], {}) if len(seasons_sorted) > 1 else {}
            p["stats"] = cur
            p["prior_stats"] = pri
        # assign jersey numbers: players without numbers go lower on depth chart
        JERSEY_RANGES = {
            0: (1, 19), 1: (20, 49), 2: (30, 49), 3: (80, 89), 4: (40, 49),
            5: (50, 79), 6: (50, 79), 7: (50, 79), 8: (50, 79), 9: (50, 79),
            10: (90, 99), 11: (90, 99), 12: (90, 99),
            13: (40, 59), 14: (40, 59), 15: (40, 59),
            16: (20, 49), 17: (20, 49), 18: (20, 49),
            19: (1, 19), 20: (1, 19),
        }
        used_numbers = set()
        for p in chosen:
            j = p.get("jersey", 0) or 0
            p["_had_jersey"] = j > 0
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
        # sort: players with original jersey numbers first, then by production
        # (stats volume) then experience. This puts starters (most productive/
        # experienced) at the top of the depth chart.
        def _depth_key(p):
            st = p.get("stats", {}) or {}
            touches = (st.get("receptions", 0) or 0) + (st.get("rushingAttempts", 0) or 0) + (st.get("completions", 0) or 0) + (st.get("tackles", 0) or 0)
            jersey_priority = 0 if p.get("_had_jersey", False) else 1
            return (jersey_priority, -touches, -(p.get("experience", 0) or 0))
        chosen.sort(key=_depth_key)
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
                 "stats": {}, "prior_stats": {}, "_pgid": pgids[len(chosen)] if len(chosen) < len(pgids) else 0,
                 "_had_jersey": False}
            chosen.append(p)
        # assign jersey numbers to walk-ons too
        for p in chosen:
            if (p.get("jersey", 0) or 0) == 0:
                for num in range(20, 100):
                    if num not in used_numbers:
                        p["jersey"] = num
                        used_numbers.add(num)
                        break
        team_to_players[tg] = chosen
        all_players.extend(chosen)

    # Check if any player has current-season stats
    has_current_stats = any(str(season) in p.get("stats", {}) for p in all_players)
    if not has_current_stats:
        log(f"  WARNING: No {season} stats found. Using {prior} stats only (100% prior season).")
        log(f"  This is normal for pre-season runs.")
        current_weight = 0.0
    else:
        current_weight = 0.6
    # Check if ESPN roster seems stale (no freshmen for a future season)
    freshmen_count = sum(1 for p in all_players if (p.get("_class") or "").upper().startswith("FR") or (p.get("experience") or 0) == 0)
    if season > 2026 and freshmen_count == 0:
        log(f"  WARNING: No freshmen found. ESPN roster may not be updated for {season} yet.")
    log(f"[4/6] Rating {len(all_players)} players...")
    rate_players(all_players, current_weight=current_weight)

    log(f"[5/6] Writing DB...")
    base_db = TDBFile(open(db_path, "rb").read())
    # fetch Top 25 rankings
    ranking_map = None
    if rankings:
        log("  Fetching AP Top 25 + Coaches Poll...")
        from roster_gen.sources.rankings import build_ranking_map
        ncaa_names = [t["name"] for t in teams(db) if t["type"] == 0]
        ranking_map = build_ranking_map(tmap)
        ranked = sum(1 for v in ranking_map.values() if v[0] > 0)
        log(f"  Ranked teams: {ranked}")
    log(f"  Writing {len(all_players)} players and depth charts...")
    write_roster(db, team_to_players, base_db=base_db, realignment=realignment,
                 rankings=ranking_map, log=log)
    log("  Writing team ratings and conference data...")
    # save db
    new_db = db.build()
    # Pad to the original container size (1,433,600 bytes) with zero plaintext.
    # The PS3 expects this full size; trailing bytes are zero-filled padding.
    CONTAINER_SIZE = 1433600
    if len(new_db) < CONTAINER_SIZE:
        new_db = new_db + b"\x00" * (CONTAINER_SIZE - len(new_db))
    with open(os.path.join(work, "USR-DATA"), "wb") as f:
        f.write(new_db)

    log(f"[6/6] Encrypting save -> {out_dir}")
    # Set ACCOUNT_ID to the user's own PS3 account (from their save) so the
    # PS3 recognizes the save as theirs. Falls back to neutral zeros if unknown.
    if rename:
        # Use base's own SFO (preserves account ID), update directory name only
        encrypt_save(work, save_dir, base_dir, sfo_source_dir=base_dir, account_id=None)
    else:
        # Keep original PARAM.SFO byte-identical (no rename, no account change)
        import shutil
        shutil.copy2(os.path.join(base_dir, "PARAM.SFO"), os.path.join(save_dir, "PARAM.SFO"))
        # still need to re-encrypt USR-DATA and rebuild PFD
        from roster_gen.ps3.save import encrypt_save as _es
        # call a minimal version: just encrypt + rebuild PFD, don't touch SFO
        from roster_gen.ps3.pfd import PFD
        pfd = PFD(base_dir)
        with open(os.path.join(work, "USR-DATA"), "rb") as f:
            plain = f.read()
        enc = pfd.encrypt_file("USR-DATA", plain)
        with open(os.path.join(save_dir, "USR-DATA"), "wb") as f:
            f.write(enc)
        for name in ("HED-DATA", "ICON0.PNG"):
            src = os.path.join(base_dir, name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(save_dir, name))
        pfd.rebuild(save_dir, {"USR-DATA": enc})

    # report + csv in the output root
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
    log(f"Done. Output root: {out_dir}")
    log(f"Save folder: {save_dir}")
    log("")
    log("=== WHERE TO COPY ON YOUR PS3 ===")
    log("USB drive: copy the 'PS3' folder to the ROOT of your USB drive.")
    log("  Then on PS3: Game -> Save Data Utility (PS3) -> copy from USB to HDD.")
    log("FTP: upload 'BLUS31159-ROSTER-...' into /dev_hdd0/home/00000001/savedata/")
    log("  (skip the PS3/SAVEDATA wrapper for FTP)")
    log("Then launch NCAA Football 14.")
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
