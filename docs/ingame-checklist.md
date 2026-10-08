# In-game checklist

What can only be checked with War Thunder installed (Windows). Written on 2026-10-08 after work done on a
Mac without the game. Tick each line, note what you see, then fix or remove the item.

Setup: `python -m wtftd` from this repository (or the exe built from `main`), custom vehicles on (default).
After a mission is created: start War Thunder → **Single missions → User missions**.

## 1. Countermeasures: flares / chaff split (new, never tested in game)

**What was built.** In the Ammunition step, an aircraft whose countermeasure launcher takes both flares and
chaff shows two counts (flares, chaff) and a slider. Their sum is the launcher's capacity (`cap × n`
launchers).

**How the mission is written** (`wtftd/mission.py` → `write_bullets`):

| Setting | Mission slots |
|---|---|
| all flares (default) | the launcher's slot: `bullets<i>=""`, count = total. Same as before. |
| all chaff | the launcher's slot: `bullets<i>="countermeasures_launcher_chaff…"`, count = total. Same as before. |
| mix | the launcher's slot: `bullets<i>=""`, count = flares; **plus** the first slot no gun uses: `bullets<j>="countermeasures_launcher_chaff…"`, count = chaff |

`<i>` is the launcher's index in WTFTD's ammo groups (`details.json` → `am`, guns first). Example F-14B,
40 flares + 20 chaff: `bullets0="" 676`, `bullets1="" 40`, `bullets2="countermeasures_launcher_chaff" 20`.

**Tests**, for each aircraft: create the mission, fly it, read the countermeasure counts in the HUD (weapons
panel) and drop some of each.

| Aircraft (id) | Why | Set | Expect |
|---|---|---|---|
| F-14B (`f_14b`) | 1 launcher, guns first in its file | 40 flares + 20 chaff | 40 / 20 |
| MiG-29SMT (`mig_29smt_9_19`) | launcher declared **before** the gun in its file | 10 flares + 20 chaff | 10 / 20 |
| Su-25 (`su_25`) | 4 launchers (`n=4`, total 256) | 200 + 56 | 200 / 56 |
| any of them | regression | all flares, then all chaff | as before |

**If the mix is wrong**, the slot numbering is the issue. Variants to try, in this order (edit
`write_bullets`, re-create the mission, retest):

- **B: pair in consecutive slots.** Flares in the launcher's slot `i`, chaff in `i+1`, the following guns
  shifted by one. Matches the game scripts: a split launcher is two linked bullet groups on the same gun.
- **C: Gaijin's own training missions.** In `mis.vromfs.bin_u/gamedata/missions/training/modifications/`,
  `tank_sam_ir_photocontrast_mode_tft` gives Su-25 targets `bullets0="" 15` + `bullets1="countermeasures_launcher_chaff" 15`
  (15 flares + 15 chaff?), and `aircraft_countermeasures_chaff_sky` gives the MiG-29SMT
  `bullets0="countermeasures_launcher_chaff"`. In both, the launcher uses slots 0 and 1, before the gun.
- **D: game group order.** Slot = order in which the unit's `modifications` block first names a bullet
  set of each weapon (MiG-29SMT: countermeasures first, then the GSh-30-1).

Where the game decides this (datamine, `gui.vromfs.bin_u/scripts/weaponry/`): `bulletsinfo.nut`
(`getBulletsInfoForPrimaryGuns`, `getLinkedGunIdx`, `isPairBulletsGroup`), `unitbulletsmanager.nut`
(`changeBulletsCount`: the second group of a pair gets what the first leaves), `unitbulletsgroup.nut`.
Checking the official missions against three numbering rules matched only about half of them each (they may be old),
so only the game can settle it.

## 2. Gun belts on aircraft (existing behaviour, worth one check)

WTFTD writes the belt of its ammo group `i` into `bullets<i>` (guns first). The game may number slots
differently (see variant D) or find a named belt by its name whatever the slot. Check one aircraft where the
order differs:

- MiG-29SMT: pick a non-default GSh-30-1 belt (e.g. *Stealth*), fly, check the belt in game (tracers, or the
  belt name in the weapons panel). If it is ignored, apply the same numbering fix as for countermeasures.

## 3. Ammunition icons (UI only)

Shell icons (tanks), belt icons (aircraft, helicopters, ships) and flare / chaff icons come from the game's own
table (`aces.vromfs.bin_u/config/gui.blkx` → `bullet_icons`, written to `data/bullet_icons.json`). Data schema
went from 7 to 8: an installed copy rebuilds itself at first launch. Check: the rebuild happens once, the icons
match the hangar's.

## 4. Windows regressions from the macOS work (v0.15.0)

- The exe opens in its Edge / Chrome app window and **quits when that window is closed** (Windows still uses
  `proc.wait()`; the close beacon is macOS only).
- Game detection (Steam and standalone), **Launch War Thunder**, **Open folder** (UserMissions).
- Settings: game folder and Oodle placeholders show Windows paths.
- First launch: language picker above the logo, translated steps under the progress bar, no raw log
  unless there is an error.
- Opening a vehicle: every setup step starts closed.

## 5. macOS (needs a Mac with the game)

Never run with the game: detection inside `WarThunderLauncher.app`, launch, missions in `UserMissions`
inside the bundle, custom vehicle files (the CDK wiki says the Mac game may reset `content/` at launch).
