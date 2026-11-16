"""roster-gen command-line entry point."""
import argparse
import os
import sys

from roster_gen import paths


def cmd_inspect(args):
    from roster_gen.pipeline import _detect_platform
    if not _require_base(args):
        return 2
    base = os.path.abspath(os.path.expanduser(args.base))
    kind = _detect_platform(base)
    from roster_gen.db.roster import teams, players, position_name
    from roster_gen.eadb import TDBFile
    if kind == "ps3":
        from roster_gen.ps3.save import decrypt_save
        work = args.work or str(paths.WORK_DIR / "run")
        db_path, _ = decrypt_save(base, work)
        raw = open(db_path, "rb").read()
        print("platform: PS3")
    else:
        from roster_gen.xbox.save import XboxSave
        save = XboxSave(base)
        raw = save.db_bytes
        print(f"platform: Xbox 360   profile: {save.profile_id}   "
              f"title: {save.title_id:08X}")
        print(f"package: {save.name}   db at {save.db_offset} ({save.db_size} bytes)")
    db = TDBFile(raw)
    probs = db.verify()
    print("verify:", "OK" if not probs else probs)
    ts = teams(db)
    print("teams:", len(ts), "with players:", sum(1 for t in ts if t["type"] == 0))
    fbs = [t for t in ts if t["type"] == 0]
    for t in fbs[:5]:
        ps = players(db, t["tgid"])
        print(f"  {t['name']!r} (TGID {t['tgid']}): {len(ps)} players")
    print("total players:", len(players(db)))
    return 0


def cmd_copy(args):
    """Byte-identical round-trip proof: decrypt then re-encrypt a save."""
    from roster_gen.pipeline import _detect_platform
    if not _require_base(args):
        return 2
    base = os.path.abspath(os.path.expanduser(args.base))
    kind = _detect_platform(base)
    out = args.out
    os.makedirs(out, exist_ok=True)
    if kind == "xbox360":
        from roster_gen.xbox.save import XboxSave
        save = XboxSave(base)
        out_path = save.save(out)
        a = open(base, "rb").read()
        b = open(out_path, "rb").read()
        print(os.path.basename(out_path), "identical" if a == b else "DIFFERS",
              len(a), len(b))
        return 0
    from roster_gen.ps3.save import decrypt_save, encrypt_save
    work = args.work or str(paths.WORK_DIR / "copy")
    decrypt_save(base, work)
    encrypt_save(work, out, base)
    # verify byte-identical
    for name in ("PARAM.PFD", "USR-DATA"):
        a = open(os.path.join(base, name), "rb").read()
        b = open(os.path.join(out, name), "rb").read()
        print(name, "identical" if a == b else "DIFFERS", len(a), len(b))
    return 0


def _require_base(args):
    if not args.base:
        print("No base save given. Pass --base /path/to/BLUS#####-ROSTER-XXXX "
              "or /path/to/ROSTER-ROSTER14", file=sys.stderr)
        return False
    return True


def cmd_run(args):
    from roster_gen.pipeline import run
    if not _require_base(args):
        return 2
    base = args.base
    out = args.out
    resign = True
    try:
        out_dir = run(args.year, base, out, rename=not args.keep_name, realignment=args.realignment,
                      rankings=not args.no_rankings, workers=args.workers, skip_stats=args.skip_stats,
                      platform=args.platform, resign=resign)
        print(f"Output: {out_dir}")
        return 0
    except Exception as e:
        import traceback; traceback.print_exc()
        return 1


def cmd_resign(args):
    from roster_gen.xbox.resign import resign_with_horizon
    from roster_gen.xbox.horizon import find_horizon
    path = os.path.abspath(os.path.expanduser(args.file))
    hr = args.horizon or None
    if hr:
        hr = os.path.abspath(os.path.expanduser(hr))
    else:
        hr = find_horizon()
    res = resign_with_horizon(path, horizon_path=hr, launch_gui=not args.no_launch)
    print(res.message)
    if res.backup_path:
        print(f"Backup: {res.backup_path}")
    return 0 if res.ok or res.mode == "manual" else 1


def cmd_check_horizon(args):
    from roster_gen.xbox.horizon import find_horizon, horizon_version
    hr = find_horizon()
    if hr is None:
        print("Horizon: NOT FOUND")
        print("Set NCAA_HORIZON_PATH or install Horizon to enable stock-console re-signing.")
        return 1
    print(f"Horizon: {hr}")
    v = horizon_version(hr)
    if v:
        print(f"Version: {v}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="roster-gen")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("inspect", help="inspect a base save")
    sp.add_argument("--base", default=paths.DEFAULT_BASE)
    sp.add_argument("--work", default=None)
    sp.set_defaults(func=cmd_inspect)
    sp = sub.add_parser("copy", help="byte-identical round-trip of a save")
    sp.add_argument("--base", default=paths.DEFAULT_BASE)
    sp.add_argument("--out", required=True)
    sp.add_argument("--work", default=None)
    sp.set_defaults(func=cmd_copy)
    sp = sub.add_parser("run", help="generate a roster for a season year")
    sp.add_argument("year", type=int)
    sp.add_argument("--base", default=paths.DEFAULT_BASE)
    sp.add_argument("--out", default=None)
    sp.add_argument("--keep-name", action="store_true", help="keep original save name (PS3 only)")
    sp.add_argument("--platform", default="auto", choices=("auto", "ps3", "xbox360"),
                    help="base save platform (default: detect from the file)")
    sp.add_argument("--realignment", action="store_true", help="apply 2026 conference realignment (Phase A)")
    sp.add_argument("--no-rankings", action="store_true", help="skip Top 25 ranking updates")
    sp.add_argument("--workers", type=int, default=10, help="number of parallel downloads (default 10)")
    sp.add_argument("--skip-stats", action="store_true", help="skip stats fetching (instant, uses priors only)")
    sp.set_defaults(func=cmd_run)
    sp = sub.add_parser("resign", help="re-sign an already generated Xbox 360 roster with Horizon")
    sp.add_argument("file", help="path to a ROSTER-* file")
    sp.add_argument("--horizon", default=None, help="path to Horizon executable (overrides detection)")
    sp.add_argument("--no-launch", action="store_true", help="do not launch Horizon's GUI; print instructions only")
    sp.set_defaults(func=cmd_resign)
    sp = sub.add_parser("check-horizon", help="detect a Horizon installation")
    sp.set_defaults(func=cmd_check_horizon)
    sp = sub.add_parser("serve", help="run the local web UI")
    sp.add_argument("--port", type=int, default=8765)
    sp.set_defaults(func=cmd_serve)
    args = p.parse_args(argv)
    return args.func(args)


def cmd_serve(args):
    import uvicorn
    from roster_gen.web.app import app
    uvicorn.run(app, host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
