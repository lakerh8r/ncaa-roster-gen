# NCAA Roster Generator — Ratings Specification (v1)

This document is the approved spec for how a player's ~40 NCAA 14 attributes are
derived from real-world data. It is the input to the implementation. Every
formula and weight below lives in an editable YAML file (`ratings/formulas.yaml`)
and the applied version's hash is recorded in each run's report.

## 1. Principles

1. **Transparent and auditable.** Every attribute is a documented function of
   measurable inputs. No black-box ML.
2. **Hybrid production + measurables.** Production attributes are percentile-ranked
   within position across FBS; physical attributes (height, weight, speed,
   strength) use absolute thresholds where real data exists, otherwise
   estimates from recruiting profile + position/weight norms.
3. **Position-specific.** A QB's Overall weights Throw Power/Accuracy; a DT's
   weights Strength/Block Shedding. Attribute lists differ by position.
4. **Calibrated to the base file.** The base 2013 roster's per-position attribute
   distributions are the target curve (it is the game's native scale). New
   ratings are fit to those distributions, with caps adjusted for 2026 talent
   depth. This makes the output feel native to NCAA 14.
5. **Small-sample shrinkage.** Production from < N snaps/games is shrunk toward a
   prior (recruiting composite + class + career stats). Confidence is tagged
   per player: `measured`, `prior`, or `projected`.
6. **Strength-of-schedule adjustment.** Production is adjusted by a mild
   conference/opponent factor (±5 rating points max), visible in the rationale.

## 2. Data pipeline

```
season year (e.g. 2026)
  -> scrape official rosters (per team) -> players (name, pos, yr, ht, wt, jersey, hometown)
  -> scrape stats (per player, per season) -> season stats
  -> blend: 60% season N (to date) + 40% season N-1 (full), rate-normalized
  -> compute attributes per position formula
  -> shrink small samples toward prior
  -> calibrate to base distributions
  -> compute OVR
  -> write DB + report
```

For a completed season, use 100% of that season. For a future season with no
games, use the prior season + recruiting projection. Weights are configurable.

Stats are **rates** (per game / per play / per snap), normalized for team tempo
and opponent, never raw totals, whenever the source supports it.

## 3. Season blending

- `season_year` S = the year the season kicks off (Aug S).
- Blend = `w_new * stats(S, to_date) + (1-w_new) * stats(S-1, full)`.
- Default `w_new = 0.6`. Configurable.
- If `stats(S)` is empty, fall back to `stats(S-1)` at weight 1.0 and tag
  players as `prior` where applicable.

## 4. Attribute domains

NCAA 14 player attributes are integers 0–99 (stored in `PLAY` fields, see
`EA_DB_FORMAT.md` Appendix A). Height is inches, weight is pounds (stored as
pounds-160), jersey 0–127, year 0–7, position 0–20.

## 5. Universal physical attributes

| Attribute | Field | Method |
|---|---|---|
| Height | PHGT | inches from roster |
| Weight | PWGT | pounds-160 from roster |
| Speed | PSPD | see §6 |
| Acceleration | PACC | speed-derived, position-specific (typically speed-2..speed+1) |
| Agility | PAGI | position norm + elusiveness/short-area production proxy |
| Strength | PSTR | see §6 |
| Stamina | PSTA | snap share + class; starters 85–95, backups 70–85 |
| Injury | PINJ | availability history; default 80 if unknown |
| Jump | PJMP | position norm + recruiting vertical where available |

## 6. Speed and strength estimation

Public measurables (40 time, bench, squat) are rarely available. Estimate:

- **Speed**: blend of (a) recruiting-profile 40 time / SPARQ where recorded,
  (b) position/weight norm, (c) production proxies (explosive plays, yards per
  carry/reception, sack/TFL rate for defenders). Apply position caps (e.g. OL
  55–78, WR 80–99, DB 82–99). Use official combine/pro-day numbers for
  upperclassmen when available.
- **Strength**: weight + position + recruiting composite; OL/DL 75–99, skill
  positions 45–75. Adjust by playing weight vs position norm.
- **Awareness** (PAWR): see §7.

## 7. Awareness / Play Recognition / intangibles

Formula from experience (class, career starts), production consistency,
awards/all-conference honors, turnover and penalty rates, with position-specific
weights. Inputs recorded in the rationale. Cannot be measured directly; tagged
`prior`/`projected` when experience < 1 season.

## 8. Per-position attribute formulas

Each position gets the attributes it uses; unused attributes are set to a
position-appropriate default (usually 40–50). Production attributes are
percentile-ranked within position across FBS after SOS adjustment and shrinkage.

### QB (pos 0)
- Throw Power (PTHP): arm strength proxy (recruiting + deep-ball rate) + size
- Throw Accuracy (PTHA): completion % (adjusted), on-target rate, INT rate
- Awareness (PAWR): experience, TD/INT, third-down conversion
- Play Recognition (PPRC): not used (defensive); set default
- Speed (PSPD), Acceleration (PACC), Agility (PAGI): from §6
- Trucking (PTRK), Break Tackle (PBTK), Carry (PCAR): rushing production
- Release (RELS): pocket time / sack rate

### HB (pos 1) / FB (pos 2)
- Speed, Acceleration, Agility, Strength, Trucking, Break Tackle, Carry,
  Elusiveness (PESV), Juke (PJMV), Spin (PSMV), Ball Carrier Vision (PBCV),
  Catch (PCTH), Catch In Traffic (TRAF), Route Running (PRTR) for receiving backs
- Awareness from usage/production consistency

### WR (pos 3)
- Speed, Acceleration, Agility, Catch, Catch In Traffic, Spec Catch (SPCT),
  Route Running, Release, Jump, Elusiveness, Juke, Spin

### TE (pos 4)
- Catch, Route Running, Release, Block Shedding (PBSH), Pass Blocking (PPBK),
  Run Blocking (PRBK), Strength, Speed

### OL (pos 5–9: LT, LG, C, RG, RT)
- Pass Blocking, Run Blocking, Pass Blocking Strength (PPBS), Run Blocking
  Strength (PRBS), Pass Blocking Footwork (PPBF), Run Blocking Footwork (PBFW),
  Impact Blocking (PIBL), Strength, Awareness, Discipline (PDIS)
- Inputs: team sack rate, rushing yards before contact proxy, penalties,
  starts, awards, size

### DL (pos 10–12: LE, RE, DT)
- Block Shedding, Tackling (PTAK), Hit Power (PHIT), Finesse Moves (PFMV),
  Power Moves (PPMV), Spin Move (PSMV), Pursuit (PPRS), Strength, Speed,
  Awareness
- Inputs: sacks, TFLs, pressures, tackles, snap share

### LB (pos 13–15: LLB, MLB, RLB)
- Tackling, Hit Power, Block Shedding, Pursuit, Play Recognition (PPRC),
  Man Coverage (PMCV), Zone Coverage (PZCV), Speed, Strength, Awareness
- Inputs: tackles, TFLs, sacks, INTs, PDs, snap share

### DB (pos 16–18: CB, FS, SS)
- Man Coverage, Zone Coverage, Play Recognition, Pursuit, Tackling, Hit Power,
  Speed, Agility, Awareness, Jump
- Inputs: INTs, PDs, tackles, yards allowed (where available), snap share

### K (pos 19) / P (pos 20)
- Kick Power (PKPR), Kick Accuracy (PKAC), Punt power/accuracy derived from
  average/net, touchback rate, long attempts
- Distance-bucketed FG% (not a single FG%)

## 9. Overall (OVR)

`POVR` is a stored 7-bit field (0–127, game uses 0–99). Computed per position
from a weighted sum of the relevant attributes, using position-specific weights
calibrated so that the resulting distribution matches the base file's OVR
distribution. Stored value = round(weighted sum), clamped 0–99.

## 10. Small-sample shrinkage

For players with fewer than `MIN_SNAPS` (configurable, default 200) or `MIN_GAMES`
(default 4) of college data:

- weight `w = min(1, samples / threshold)`.
- attribute = `w * measured + (1-w) * prior`, where prior is built from
  recruiting composite (stars/rating), class, position norm, and career stats.
- Tag the player `prior` (w < 0.5) or `measured` (w >= 0.5). Players with no
  college data at all are tagged `projected`.

Recruiting composite is a 0–99 score derived from 247/On3 consensus rating if
available, otherwise a class/position prior.

## 11. Strength-of-schedule adjustment

Production inputs are multiplied by a conference factor before percentile
ranking. Factors are configurable (default Power 4 ≈ 1.0, G5 ≈ 0.92, FCS ≈ 0.85).
Applied as ±5 rating points max after percentile conversion. Factor and
adjustment are recorded in the rationale.

## 12. Roster construction

- Keep the base's 2013 team identities and conferences (v1). Update coach
  names/staff to 2026 (skills unchanged).
- For each base team that has 2026 data, replace its existing players with
  current roster players, preserving the base per-team player count.
- Fill position shortfalls with generated walk-ons (rating 40–55) to meet
  configurable minimums per position group.
- Single primary position per player (modern label mapped via deterministic
  rules: EDGE→DE if ≥250 lbs else OLB; ATH→highest-need position; etc.).
- Two-way players: single primary position, noted in the report.
- Long snappers: position in PLAY set to TE (or C), plus a DCHT entry as LS.
- KR/PR: assigned in DCHT (codes 21/22) from the best returners; no extra
  PLAY row.
- Impact-player slots (TEAM.TSI1/TMPI/TPIO) re-pointed to the top players by
  OVR (≥1 offensive and ≥1 defensive).
- Depth chart (DCHT) regenerated per team from published charts when
  available, otherwise from computed depth (snap share/stats → class →
  recruiting rank).
- Team ratings (TROF, TROV, TRST, per-position TR*) recomputed from the new
  roster; prestige (TPRX) and conference left as-is.

## 13. Name handling

- First name field = 11 bytes, last name = 13 bytes (Latin-1/ASCII).
- Shortening: drop middle names/initials first, then truncate; report every
  change. If a first name still exceeds 11 bytes, use first initial + last name.
- Jersey numbers from the 2026 roster; duplicates renumbered and reported.
- Height in inches, weight in pounds (stored pounds-160), hometown city/state.

## 14. Confidence tags

Each player carries a tag in the report/CSV:
- `measured` — ≥ MIN_SNAPS and ≥ MIN_GAMES of college data.
- `prior` — some data but below threshold; shrunk.
- `projected` — no college data; recruiting prior only.

## 15. Validation

- PFD HMACs match after rebuild.
- Decrypt → re-encrypt byte-identical.
- DB parse → serialize byte-identical (within db_size).
- Report lists: per-team coverage %, confidence mix, top-100 players, every
  renumbered/truncated/skipped player, diff vs base, and the config hash.
- Final acceptance: manual load test on PS3/RPCS3.
