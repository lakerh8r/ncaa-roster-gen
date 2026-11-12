"""roster-gen command-line entry point."""
import argparse
import os
import sys

DEFAULT_BASE = "/home/lakerh8r/Downloads/NCAA14RosterPack/13-14 Release Year NCAA14/PS3 end of season 2013-14 Roster posted by majesty95/PS3 end of season 2013-14 Roster posted by majesty95/PS3/SAVEDATA/BLUS31159-ROSTER-JHASLEY10"


def cmd_inspect(args):
    from roster_gen.ps3.save import decrypt_save
    from roster_gen.db.roster import teams, players, position_name
    work = args.work or "/tmp/opencode/scratchpad/run"
    db_path, _ = decrypt_save(args.base, work)
    from roster_gen.eadb import TDBFile
    db = TDBFile(open(db_path, "rb").read())
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
    from roster_gen.ps3.save import decrypt_save, encrypt_save
    work = args.work or "/tmp/opencode/scratchpad/copy"
    out = args.out
    os.makedirs(out, exist_ok=True)
    decrypt_save(args.base, work)
    encrypt_save(work, out, args.base)
    # verify byte-identical
    import filecmp, hashlib
    for name in ("PARAM.PFD", "USR-DATA"):
        a = open(os.path.join(args.base, name), "rb").read()
        b = open(os.path.join(out, name), "rb").read()
        print(name, "identical" if a == b else "DIFFERS", len(a), len(b))
    return 0


def cmd_run(args):
    year = args.year
    print(f"Season start year: {year} (season {year}-{str(year+1)[-2:]})")
    print("run: scraping/rating not yet implemented in this build.")
    print("Use 'roster-gen copy' to validate the save pipeline.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="roster-gen")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("inspect", help="inspect a base save")
    sp.add_argument("--base", default=DEFAULT_BASE)
    sp.add_argument("--work", default=None)
    sp.set_defaults(func=cmd_inspect)
    sp = sub.add_parser("copy", help="byte-identical round-trip of a save")
    sp.add_argument("--base", default=DEFAULT_BASE)
    sp.add_argument("--out", required=True)
    sp.add_argument("--work", default=None)
    sp.set_defaults(func=cmd_copy)
    sp = sub.add_parser("run", help="generate a roster for a season year")
    sp.add_argument("year", type=int)
    sp.add_argument("--base", default=DEFAULT_BASE)
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_run)
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
