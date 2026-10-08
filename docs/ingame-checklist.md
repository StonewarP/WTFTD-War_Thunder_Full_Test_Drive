# In-game checklist

What can only be checked with War Thunder installed (Windows). Written on 2026-10-08 after work done on a
Mac without the game. Tick each line, note what you see, then fix or remove the item.

Setup: `python -m wtftd` from this repository (or the exe built from `main`), custom vehicles on (default).
After a mission is created: start War Thunder → **Single missions → User missions**.

## 1. Countermeasures: flares / chaff split

**What was built.** In the Ammunition step, an aircraft whose countermeasure launcher takes both flares and
chaff shows two counts (flares, chaff) and a slider. Their sum is the launcher's capacity (`cap × n`
launchers); they move by steps of `n`.

**Findings (2026-10-08, Windows, F-14B / MiG-29SMT / Su-25, CDK custom units)**

Untagged `bullets<i>` (what official missions use) bind to weapons in an order of the game's own that
differs between aircraft: F-14B launcher = slots 0-1, MiG-29SMT = slots 1-2, Su-25 = 0-1 (Gaijin's own
Su-25 missions). No rule from the datamine (wpcost order, `getLinkedGunIdx` with 6 sets, group order with
pairs) matched all the runs. Probe results that settled it: F-14B `bullets0="" 17` + `bullets1=chaff 43`
→ 17 / 43; MiG `bullets1="" 7` + `bullets2=chaff 23` → 14 / 46 (counts are **per launcher**). A pair whose
counts don't fit the launcher falls back to the game's default (full of flares, or of the named kind).
Gun belts (Stealth) were applied from any slot.

How the game itself spawns an aircraft (`gui.vromfs.bin_u/scripts/respawn/respawn.nut`): active bullet
groups one after the other, `bullets<i>` = set name (`""` for a default set), `bulletCount<i>` = count per
gun × `maxCntPerPilon`, and **`bulletsWeapon<i>` = the weapon's blk name** (`countermeasure_split_launcher_jet`,
`cannonM61A1`); 6 sets (`BULLETS_SETS_QUANTITY`), empty ones `""`. A split launcher is two groups (flares,
chaff) on the same weapon; a group at 0 is left out.

**Round 4: fix** (`mission.py` `write_bullets`, aircraft / helicopters only): same layout, with
`bulletsWeapon<i>` from `details.json` `am[].p`, counts per launcher. Missions do read `bulletsWeapon<i>`
(no official mission uses it).

| Aircraft | Set | Written (`bullets` / count / `bulletsWeapon`) | Expect |
|---|---|---|---|
| F-14B | 40 + 20, Stealth | 0: `M60_stealth` 676 `cannonM61A1`; 1: `""` 40 launcher; 2: chaff 20 launcher | 40 / 20, no tracers |
| MiG-29SMT | 20 + 40, Stealth | 0: Stealth 150 `cannonGSh_301`; 1: `""` 10; 2: chaff 20 | 20 / 40, no tracers |
| Su-25 | 200 + 56, Stealth | 0: Stealth 250 `cannonGSh_30_2`; 1: `""` 50; 2: chaff 14 | 200 / 56, no tracers |

- [x] Round 4 checked in game (2026-10-08): all three exactly as expected, Stealth belts included.
- [x] Round 5: F-14B all chaff → 60 chaff; Su-25 all flares → 256 flares; Rafale C F3, two launcher types
  (small 12 + 24, large 8 + 8) → 20 flares / 32 chaff in the HUD (it adds both launcher types).
- [x] MiG-29SMT (CDK custom unit, ground start on Sinai): the engines kept cutting out, it could not take
  off. Round 5: no cheats / immortal without the 1 s `unitRestore` full repair / other cheats → all take off.
  Cause: the immortal cheat's full repair every second restarts the engines. Fix (`mission.py`
  `apply_cheats`): aircraft and helicopters keep `isImmortal` + `invulnerabilityTimer` (+ raised hit points
  in custom vehicles), without the repair loop; ground vehicles and ships unchanged.
- [x] MiG-29SMT with the fix (`wtftd_cmtest_mig_29smt_9_19`, immortal, targets shooting): takes off.
- [x] Stays invulnerable under fire (copy of that mission with Sinai's targets switched from `hold_fire`
  to `fire_at_will`: the test-flight scenarios' targets never shoot, whatever WTFTD's passive option).

## 2. Gun belts on aircraft

- [x] Stealth belts applied on the MiG-29SMT from slots 0, 3 and 4 (rounds 1, 3, probe d).
- [x] With `bulletsWeapon`: Stealth belts on the F-14B, MiG-29SMT and Su-25 (round 4).

## 3. Ammunition icons (UI only)

Shell icons (tanks), belt icons (aircraft, helicopters, ships) and flare / chaff icons come from the game's own
table (`aces.vromfs.bin_u/config/gui.blkx` → `bullet_icons`, written to `data/bullet_icons.json`). Data schema
went from 7 to 8: an installed copy rebuilds itself at first launch. Check: the rebuild happens once, the icons
match the hangar's.

- [x] 2026-10-08, Windows: rebuild to schema 8 OK (game v2.59.0.60, 58 s), icons show in the Ammunition step.
- [ ] Icons compared with the hangar's.

## 4. Windows regressions from the macOS work (v0.15.0)

- [x] The app opens in its Edge / Chrome app window and **quits when that window is closed** (Windows still uses
  `proc.wait()`; the close beacon is macOS only). Checked from source (`python -m wtftd`), not the exe.
- [x] Game detection (Steam). [ ] Standalone, **Launch War Thunder**, **Open folder** (UserMissions).
- [x] Settings: game folder and Oodle placeholders show Windows paths.
- [ ] First launch: language picker above the logo, translated steps under the progress bar, no raw log
  unless there is an error.
- [x] Opening a vehicle: every setup step starts closed.
- [x] Found and fixed on the way: `boot()` could run before `compare.js` / `weapons.js` were loaded
  (`bindCompare` / `bindWeapons is not defined`), and My missions guessed the vehicle from the file name.

## 5. macOS (needs a Mac with the game)

Never run with the game: detection inside `WarThunderLauncher.app`, launch, missions in `UserMissions`
inside the bundle, custom vehicle files (the CDK wiki says the Mac game may reset `content/` at launch).
