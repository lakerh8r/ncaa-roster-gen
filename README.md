# NCAA Football 14 Roster Generator

Build a playable **NCAA Football 14** (PS3) roster save for any season year from
live ESPN roster data. Ratings are recalculated from real stats, players are
assigned to NCAA 14 positions and depth charts, and the Top 25 (AP + Coaches) is
updated in-game.

The tool modifies a roster save you already own. It does **not** include the
game, any save files, or team art.

## What you need

- **Linux** (or macOS; Windows users can use the command line — see below)
- **Python 3.11+**
- **A PS3 NCAA Football 14 roster save folder** to use as the base. It must
  contain `PARAM.PFD` and `USR-DATA`, e.g. `BLUS31159-ROSTER-SOMETHING`.
  Community roster packs are widely shared; use one you already have.
- A PS3 that can copy save data from USB (CFW/HEN, or a save you can transfer
  via FTP).

## Quick start (Linux)

```bash
git clone https://github.com/lakerh8r/ncaa-roster-gen.git
cd ncaa-roster-gen
./setup.sh          # creates .venv, installs deps, adds an app-menu entry
./launch.sh         # starts the local web UI
```

Then:

1. **Base save folder** — click *Browse...* and pick your existing
   `BLUS#####-ROSTER-...` folder.
2. **Output folder** — where the generated save should go.
3. **Season start year** — e.g. `2026` for the season beginning August 2026.
4. Leave **Keep original save name** checked (this is the configuration that
   loads reliably on PS3).
5. Click **Generate** and watch the live log.

A full run takes about **2–3 minutes** the first time (~40 seconds after that,
because ESPN responses are cached).

## Copying the save to your PS3

The generator writes:

```
<output folder>/PS3/SAVEDATA/<save folder>/
```

- **USB:** copy the `PS3` folder to the **root** of the USB drive. On the PS3:
  *Game → Save Data Utility (PS3)* → select the USB device → copy the roster to
  the HDD.
- **FTP:** upload the `<save folder>` itself into
  `/dev_hdd0/home/00000001/savedata/` (no `PS3/SAVEDATA` wrapper).

Then launch NCAA Football 14 and load the roster.

## What it does

1. Decrypts the base save (`PARAM.PFD` + `USR-DATA`).
2. Matches every FBS team to ESPN and downloads rosters.
3. Downloads per-player season stats (current season + prior season).
4. Filters out graduated/inactive players and maps everyone to NCAA 14
   positions (QB, HB, FB, WR, TE, LT, LG, C, RG, RT, LE, RE, DT, LOLB, MLB,
   ROLB, CB, FS, SS, K, P).
5. Recalculates ratings (60% current season / 40% prior; 100% prior when no
   current stats exist), assigns jersey numbers, and copies body/face models
   from the closest base player so models are not distorted.
6. Writes players, depth charts, team ratings, and the AP + Coaches Top 25.
7. Re-encrypts the save and writes `report.txt` + `roster.csv` next to it.

`report.txt` is a timestamped run log with per-step timings.

## Command line

The web UI is optional; everything works from a terminal:

```bash
.venv/bin/roster-gen run 2026 --base "/path/to/BLUS31159-ROSTER-XXXX" --out ~/Downloads/NCAA14RosterPack --keep-name
.venv/bin/roster-gen inspect --base "/path/to/BLUS31159-ROSTER-XXXX"
.venv/bin/roster-gen copy --base "/path/to/..." --out /tmp/roundtrip
.venv/bin/roster-gen serve            # web UI on http://127.0.0.1:8765
```

Useful flags for `run`:

| Flag | Meaning |
|---|---|
| `--keep-name` | Keep the base save's folder name (recommended for PS3) |
| `--workers N` | Parallel downloads (default 10) |
| `--skip-stats` | Skip ESPN stats; rate from prior season only (instant) |
| `--no-rankings` | Do not touch the Top 25 |
| `--realignment` | Apply the 2026 conference alignment (**experimental**; may freeze schedule generation) |

Environment variables:

| Variable | Default |
|---|---|
| `NCAA_BASE_SAVE` | empty (browse to a save) |
| `NCAA_OUT_DIR` | `~/Downloads/NCAA14RosterPack` |
| `NCAA_WORK_DIR` | system temp dir + `/ncaa-roster-gen` |
| `NCAA_CACHE_DIR` | `~/.cache/ncaa-roster-gen` |

## Troubleshooting

- **PS3 error 8001051C (corrupted data):** make sure *Keep original save name*
  is checked. The save must keep the base folder name for the PS3 to accept it.
- **"No <year> stats found" warning:** normal before a season starts, or if you
  picked a year ESPN has no data for yet. Ratings fall back to the prior season.
- **Realignment freezes on "generating season schedule":** known issue; leave
  the realignment checkbox off.
- **Slow run / lots of retries:** delete `~/.cache/ncaa-roster-gen` to start
  fresh, or check your connection. Players without an ESPN stats page are cached
  and skipped instead of retried.
- **Xbox 360:** not supported yet. It needs a 360 base save (`.CON`) and profile
  ID for re-signing.

## Development

```bash
.venv/bin/python -m pytest -q                     # skips save tests without a base
NCAA_BASE_SAVE=/path/to/save .venv/bin/python -m pytest -q
```

Layout:

- `roster_gen/ps3/` — PS3 save crypto (`PARAM.PFD`, `PARAM.SFO`, USR-DATA)
- `roster_gen/eadb.py` — EA TDB reader/writer (see `docs/EA_DB_FORMAT.md`)
- `roster_gen/sources/` — ESPN adapters, team mapping, Top 25
- `roster_gen/ratings/` — rating engine (see `ratings_spec.md`)
- `roster_gen/db/` — roster/team/depth-chart writing and conference data
- `roster_gen/pipeline.py` — end-to-end run
- `roster_gen/web/` — local FastAPI UI

## Notes and credits

- Base-save format knowledge cross-checked against
  [bep713/madden-file-tools](https://github.com/bep713/madden-file-tools).
- The example base save used during development was a community roster posted by
  majesty95.
- ESPN data belongs to ESPN; NCAA Football 14 belongs to EA. This is a
  fan-made tool for personal use, with no affiliation.
- The PS3 save keys in `roster_gen/ps3/keys.py` are the publicly documented
  PS3 save-data keys; they are required to read and write save files.

## License

MIT — see [LICENSE](LICENSE).
