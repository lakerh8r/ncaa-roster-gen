# ncaa-roster-gen

Generate an NCAA Football 14 (PS3) roster save for a given season year.

## Status

Foundation complete: PS3 save crypto (PARAM.PFD + USR-DATA) and the EA TDB database
reader/writer are implemented and verified byte-identical against the base save.
Scraping + rating engine + DB writing are the next phase.

## Setup

```bash
uv venv .venv --python 3.14
uv pip install -e .
```

## Usage

Inspect a base save:
```bash
roster-gen inspect --base /path/to/BLUS31159-ROSTER-...
```

Validate the save pipeline (byte-identical round trip):
```bash
roster-gen copy --base /path/to/BLUS31159-ROSTER-... --out /tmp/out
```

Run the web UI (single field: season start year):
```bash
roster-gen serve   # then open http://127.0.0.1:8765
```

Generate (pipeline not yet wired):
```bash
roster-gen run 2026
```

## Tests
```bash
.venv/bin/python -m pytest -q
```

## Key files
- `ratings_spec.md` — approved rating methodology.
- `roster_gen/ps3/pfd.py` — PARAM.PFD crypto.
- `roster_gen/ps3/save.py` — save folder decrypt/encrypt.
- `roster_gen/eadb.py` — EA TDB DB reader/writer.
- `roster_gen/db/roster.py` — roster model helpers.
- `EA_DB_FORMAT.md` (in /tmp/opencode) — full format spec.
