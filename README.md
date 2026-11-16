# NCAA Football 14 Roster Generator

Build a playable **NCAA Football 14** roster save for **PS3 or Xbox 360** for any
season year from live ESPN roster data. Ratings are recalculated from real stats,
players are assigned to NCAA 14 positions and depth charts, and the Top 25
(AP + Coaches) is updated in-game.

The tool modifies a roster save you already own. It does **not** include the
game, any save files, or team art.

## What you need

- **Windows, Linux, or macOS** (Windows steps below)
- **Python 3.11+**
- **A base roster save you already own**, either:
  - **PS3:** a save folder such as `BLUS31159-ROSTER-SOMETHING` containing
    `PARAM.PFD` and `USR-DATA`, or
  - **Xbox 360:** the `ROSTER-ROSTER14` file copied off your 360 USB drive, or
  - any larger `ROSTER-*` file your console already loads.

  Community roster packs are widely shared; use one you already have.
- **A console that can copy save data from a USB drive.** Build from a save that
  already loads on your console: the PS3 output keeps the base save's account
  ID, and the Xbox 360 output keeps the base save's profile ID (XUID).

## Quick start (Linux / macOS)

```bash
git clone https://github.com/lakerh8r/ncaa-roster-gen.git
cd ncaa-roster-gen
./setup.sh          # creates .venv, installs deps, adds an app-menu entry
./launch.sh         # starts the local web UI
```

Then:

1. **Base save** — click *Browse...* and pick your `BLUS#####-ROSTER-...`
   PS3 save folder, or your Xbox 360 `ROSTER-ROSTER14` file.
2. **Output folder** — where the generated save should go.
3. **Season start year** — e.g. `2026` for the season beginning August 2026.
4. On PS3, leave **Keep original save name** checked (this is the
   configuration that loads reliably). Xbox 360 always keeps its file name.
5. Click **Generate** and watch the live log.

A full run takes about **2–3 minutes** the first time (~40 seconds after that,
because ESPN responses are cached).

## Quick start (Windows)

Install Python 3.11+ from [python.org](https://www.python.org/downloads/) and
tick **"Add python.exe to PATH"** during setup.

Then either:

**Double-click `launch.bat`** in the repo folder. The first run creates the
environment and installs dependencies (a minute or two); after that it starts
the server and opens the browser.

**Or do it by hand** in PowerShell, from the repo folder:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\roster-gen serve
```

Then open <http://127.0.0.1:8765>. The web UI is identical to Linux; only the
launcher differs (`setup.sh` and `launch.sh` are bash-only).

`py` is the Python launcher that ships with python.org installs. If Windows
says it can't find `py`, use `python` or `python3` instead.

If you already use **WSL**, install Ubuntu from the Microsoft Store and follow
the Linux steps above instead.

## Walkthrough: PlayStation 3 (beginner)

Follow these steps end to end. You only need to do the install part once.

### 1. Install

- **Linux/macOS:** `./setup.sh` then `./launch.sh`.
- **Windows:** double-click `launch.bat`.

Your browser opens to **NCAA Football 14 Roster Generator**.

### 2. Pick your console

Click the big **PlayStation 3** button. (The page remembers this choice.)

### 3. Base save

- Click **Browse...** next to *Base save*.
- Navigate to your PS3 roster save folder (the one containing `PARAM.PFD` and
  `USR-DATA`, e.g. `BLUS31159-ROSTER-SOMETHING`) and click **Select this folder**.
- A small "Detected: PS3" badge appears.

### 4. Output folder

Leave the default (`~/Downloads/NCAA14RosterPack`) or click **Browse...** to
choose another.

### 5. Season start year

Type the season, e.g. `2026`. If ESPN has no stats for that year yet, the tool
falls back to the prior season automatically (you'll see a warning in the log).

### 6. Keep original save name

Leave **Keep original save name (recommended — PS3 rejects renamed saves)**
checked. This is the configuration that loads reliably on PS3.

### 7. Advanced options (optional)

Click **Advanced options** to expand:
- *Apply 2026 conference realignment* — leave off unless you want it
  (experimental; may freeze schedule generation).
- *Update Top 25 rankings (AP + Coaches)* — leave checked.
- *Skip stats (instant, uses priors only)* — check only for a fast test run.

### 8. Generate

Click **Generate**. A live log fills in: team mapping, scraping, rating,
writing, encrypting. A full run takes ~2-3 minutes the first time (~40 s
after that, because ESPN responses are cached). When finished you'll see
`Done! Output: ...` and `Total runtime: ...`.

### 9. Copy to your PS3

See [Copying the save to your PS3](#copying-the-save-to-your-ps3) below:
USB root `PS3` folder, then *Game -> Save Data Utility (PS3)*, or FTP into
`/dev_hdd0/home/00000001/savedata/`.

Then launch NCAA Football 14 and load the roster.

### Tips

- **PS3 error 8001051C (corrupted data):** make sure *Keep original save name*
  is checked.
- **Save belongs to another user:** build from a base save that already loads
  on your PS3 (the output keeps the base save's account ID).
- **A team shows generic players:** ESPN had no roster page for that school;
  the tool kept the base players. Logged as `no ESPN roster for <team>`.

---

## Walkthrough: Xbox 360 (beginner)

### 1. Install

Same as above (`./setup.sh` / `launch.bat`).

### 2. Pick your console

Click the big **Xbox 360** button.

### 3. Base save

- Click **Browse...** next to *Base save*.
- Navigate to your `ROSTER-ROSTER14` file (or any `ROSTER-*`) copied off your
  Xbox 360 USB drive and **click the file itself**. The path fills in.
- A small "Detected: Xbox 360" badge appears.

### 4. Output folder

Leave the default or pick another. The tool creates an
`Xbox360/Content/...` tree inside it.

### 5. Season start year

Type the season, e.g. `2026`.

### 6. Generate

Click **Generate**. Takes ~1-3 minutes. When finished you'll see
`Done! Output: ...` and `Total runtime: ...`.

If Horizon is installed, the tool re-signs automatically and the log ends
with "This save was re-signed with Horizon: it should load on a stock console."
Otherwise you'll see "Stock console? Rehash & Resign the file with Horizon
first." — install Horizon and run `roster-gen resign <file>` (or use the UI's
**Re-sign existing file...** button).

### 7. Copy to your Xbox 360

See [Copying the save to your Xbox 360](#copying-the-save-to-your-xbox-360) below:
copy the `Xbox360` folder to the **root** of a **FAT32** USB drive, then on
the console copy the roster to the hard drive from Storage, then launch
NCAA Football 14.

### "or Re-sign existing file..."

The second button is independent of Generate. Use it only if you already have a
generated `ROSTER-*` file and want to re-sign it (e.g. after moving it to
another machine). You do not run both buttons together.

### If the console says the roster is damaged or doesn't list it

That's the signature. Re-sign with Horizon (or install Horizon and re-run
Generate). Also try *System Settings -> Storage -> USB -> Configure Now* so
the drive gets indexed.

### Tips

- **USB drive must be FAT32.**
- **First run is slow** (~2-3 min); later runs ~30-60 s (cached).
- **"No 2026 stats found" warning** is normal before a season starts.
- **A team shows generic players:** ESPN had no roster page; base players kept.

---

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

## Copying the save to your Xbox 360

The generator writes the same layout the console uses on a USB drive:

```
<output folder>/Xbox360/Content/<XUID>/454109B6/00000001/ROSTER-ROSTER14
```

1. Copy the `Xbox360` folder to the **root** of a **FAT32** USB drive.
2. Plug it into the 360. In *Storage*, open the USB device and copy the roster
   file to your hard drive (same place the original came from).
3. Launch NCAA Football 14 and load the roster.

### Signing (read this)

The generator rebuilds the save's SHA-1 hash tree but **cannot re-sign it**: that
needs Microsoft's private key. So the output is *rehashed, not resigned* by
default.

- If Horizon is installed, the tool re-signs automatically (Generate → copy →
  play).
- Otherwise, run the generated `ROSTER-ROSTER14` through **Horizon** (free
  Windows tool) and use **Rehash & Resign**, then copy it to the USB drive.
  Horizon's re-signing reuses your own profile, so run it while the file sits in
  the `<XUID>` folder created by the generator.

If the console says the roster is damaged, it is almost always the signature:
re-sign it with Horizon and try again.

## Xbox 360 — how it works

The generator always writes a **rehashed** save. It never ships or uses
Microsoft's private key.

- If Horizon is installed, the web UI and `roster-gen run` re-sign
  automatically; the result loads on a stock console with no extra steps.
- If Horizon is not installed, the file is left rehashed and you re-sign
  manually with Horizon (*Rehash & Resign*) before copying to the console.
- Detect your Horizon install with `roster-gen check-horizon` or set
  `NCAA_HORIZON_PATH`.

### Re-signing an already generated file

```bash
roster-gen resign /path/to/ROSTER-ROSTER14
roster-gen resign /path/to/ROSTER-ROSTER14 --horizon /path/to/Horizon.exe
```

## What it does

1. Reads the base save: decrypts `USR-DATA` on PS3, or unpacks the STFS
   (`CON`) container and slices out the EA database on Xbox 360.
2. Matches every FBS team to ESPN and downloads rosters.
3. Downloads per-player season stats (current season + prior season).
4. Filters out graduated/inactive players and maps everyone to NCAA 14
   positions (QB, HB, FB, WR, TE, LT, LG, C, RG, RT, LE, RE, DT, LOLB, MLB,
   ROLB, CB, FS, SS, K, P).
5. Recalculates ratings (60% current season / 40% prior; 100% prior when no
   current stats exist), assigns jersey numbers, and copies body/face models
   from the closest base player so models are not distorted.
6. Writes players, depth charts, team ratings, and the AP + Coaches Top 25.
7. Re-encrypts the PS3 save (or repacks and rehashes the Xbox 360 save) and
   writes `report.txt` + `roster.csv` next to it.

`report.txt` is a timestamped run log with per-step timings.

## Command line

The web UI is optional; everything works from a terminal:

```bash
# PS3
.venv/bin/roster-gen run 2026 --base "/path/to/BLUS31159-ROSTER-XXXX" --out ~/Downloads/NCAA14RosterPack --keep-name
# Xbox 360
.venv/bin/roster-gen run 2026 --base "/path/to/ROSTER-ROSTER14" --out ~/Downloads/NCAA14RosterPack
.venv/bin/roster-gen inspect --base "/path/to/BLUS31159-ROSTER-XXXX"
.venv/bin/roster-gen copy --base "/path/to/..." --out /tmp/roundtrip
.venv/bin/roster-gen serve            # web UI on http://127.0.0.1:8765
```

The platform is detected from the base save: a folder is PS3, a `CON`/`PIRS`/
`LIVE` file is Xbox 360. Override it with `--platform ps3` or
`--platform xbox360`.

Useful flags for `run`:

| Flag | Meaning |
|---|---|
| `--platform auto\|ps3\|xbox360` | Base save type (default: detect) |
| `--keep-name` | Keep the base save's folder name (recommended for PS3; ignored on 360) |
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
| `NCAA_HORIZON_PATH` | auto-detect (Horizon executable, for stock-console re-signing) |

## Troubleshooting

- **PS3 error 8001051C (corrupted data):** make sure *Keep original save name*
  is checked. The save must keep the base folder name for the PS3 to accept it.
- **PS3 says the save belongs to another user:** the output keeps the account ID
  of the base save. Build from a base save that already loads on your PS3.
- **"No <year> stats found" warning:** normal before a season starts, or if you
  picked a year ESPN has no data for yet. Ratings fall back to the prior season.
- **Realignment freezes on "generating season schedule":** known issue; leave
  the realignment checkbox off.
- **Slow run / lots of retries:** delete `~/.cache/ncaa-roster-gen` to start
  fresh, or check your connection. Players without an ESPN stats page are cached
  and skipped instead of retried.
- **Xbox 360 says the roster is damaged / won't load:** the tool rehashes but
  cannot re-sign (no Microsoft private key). Install Horizon and re-run
  Generate (auto re-sign), or run `roster-gen resign <file>`.
  See [Copying the save to your Xbox 360](#copying-the-save-to-your-xbox-360).
- **Xbox 360 roster doesn't appear in Storage:** make sure the USB drive is
  FAT32 and that you copied the whole `Xbox360` folder to its root. The file
  must stay inside `Content/<XUID>/454109B6/00000001/`.
- **A team ends up with generic players:** ESPN occasionally has no roster page
  for a school (seen with Texas, Illinois, UMass, and Idaho at some points in
  the offseason). The generator logs `no ESPN roster for <team>; keeping base
  players` and leaves that team's existing players alone rather than writing
  68 walk-ons.

## Development

```bash
.venv/bin/python -m pytest -q                     # skips save tests without a base
NCAA_BASE_SAVE=/path/to/save .venv/bin/python -m pytest -q
NCAA_XBOX_BASE=/path/to/ROSTER-ROSTER14 .venv/bin/python -m pytest -q
```

Layout:

- `roster_gen/ps3/` — PS3 save crypto (`PARAM.PFD`, `PARAM.SFO`, USR-DATA)
- `roster_gen/xbox/` — Xbox 360 STFS container + EA DB (see `docs/STFS_FORMAT.md`)
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
