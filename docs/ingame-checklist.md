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

## 2b. Custom loadouts on fixed-preset aircraft (new)

772 aircraft (most low-BR ones) have no WeaponSlots, only fixed presets: lists of
`Weapon{trigger, blk, emitter, bullets}`. WTFTD reads every emitter those presets use (`builder.py`
`legacy_pylons` → `details.json` `lp`, presets' `ls`) and writes a custom loadout as a preset of plain weapons
on those emitters (`cdk.py`, `weapons:t="wtftd_custom"`).

| Mission | Loadout | Expect |
|---|---|---|
| `wtftd_legacy_fw190_mix` | Fw 190 A-5/U2: SC500 + 4 SC50 + 2 BR 21 (official weapons, no official preset has all three) | all carried and dropped / fired |
| `wtftd_legacy_bf109_nonstd` | Bf 109 E-3: SC250 + 2 SC50 + BR 21 rockets on points 4-5 (never on this aircraft) | rockets under the wings, fire |

- [x] Fw 190 mix (2026-10-08, works in game).
- [x] Bf 109 non-standard (2026-10-08, works in game).

## 2c. The game's other maps (new, beta)

131 maps have no official test drive. WTFTD writes a bare mission on them (`builder.py`
`build_free_scenarios`, `free_<level>_<kind>` scenarios): the player alone, at the spot where the game's own
missions put a tank / ship of the player's side (else any side), facing the same way; aircraft at 1500 m
or higher above an air unit of those missions (else the map centre), 450 km/h.

| Mission | Vehicle / map | Check |
|---|---|---|
| `wtftd_free_m1_ash_river` | M1 Abrams, Ash River (`avg_ireland`), ground | spawns on the ground, can drive |
| `wtftd_free_f14b_el_alamein` | F-14B, El Alamein (`air_africa_desert`), air start | flies away, doesn't fall |
| `wtftd_free_ship_ireland_bay` | Fletcher, Ireland bay (`avn_ireland_bay`) | spawns on water, sails |

- [x] Ground start (2026-10-09, works in game).
- [x] Air start (2026-10-09, works in game).
- [x] Naval start (2026-10-09, works in game).

## 2d. Map editor: start, zones, template units firing (new)

`wtftd_editor_test_afghan` (F-14B, Afghanistan): start set in the editor (air, 3034 m = 1500 m above the
ground, 600 km/h, heading east), the enemy base zones `bdt_t2_bomb_zone_mid_01..04` moved 3 km east, the
bases' AA (`bdt_t2_aaa_unit`, a template unit) set to Attacks.

- [x] Round 1: start ignored (2600 m, 500 km/h, heading 025): the test-flight template respawns the player in
  `spawn_area01` (its height, heading; its scripts set 500 km/h). The editor's heading was a maths angle
  (0 = east), the game shows a compass heading (0 = north). The bases' AA did engage (it is fire-at-will in
  the template already, brought in by the scripts), the aircraft was just too fast for it.
- [x] Round 2 (fix: `wtftd_start` zone + respawn into it 1 s in, speed set; compass heading in the editor;
  2 ZSU-23-4 added, fire at will): spawn at the scenario's start, a few seconds later moved to the right
  heading, speed and altitude; the ZSU-23-4 fire at you. After a crash: back at the scenario's start.
- [x] Round 3 (fix: `wtftd_dead` set when killed, back to `wtftd_start` 1 s after being alive again):
  after a crash, back at the WTFTD start (2026-10-09).
- [x] Round 4 (test flights, air start: the mission asks for an air start and the scenario's own zone
  `spawn_area0<air_spawn_point>` and its variants are moved / turned to the editor's start; only the speed
  is set 1 s in): spawn straight at ~3034 m, heading 090, no jump; 600 km/h; same after a crash: no jump (2026-10-09).
- [ ] The enemy bases appear ~3 km east of where they were.

## 2e. Ground starts without a jump, AI units with loadouts (new)

Data schema 14: `{sid}.zones.json` now says what each zone gets (`builder.zone_roles`: units the scripts put
there, the zones the player is respawned / teleported into). Ground starts: a test flight gets a runway of its
own (`addAirfield` at the start, the template's `airfield_spawn` variable kept on it, as the template itself
does for seaplanes); a tank test drive's respawn zone (`spawn01`) is moved to the start. AI units: preset +
belts written on the unit, an aircraft with custom pylons gets a custom aircraft of its own
(`pkg_user`, `wtftd_<id>_ai<n>`).

- [ ] `wtftd_r6_ground_afghan` (F-14B): parked on the Afghan runway between its two spawn points, facing NNE
  (towards the airfield centre), no jump; after a crash: same place.
- [ ] `wtftd_r6_tank_tft` (T-72A, firing range): starts 150 m north of the usual start, facing south, no jump.
- [ ] `wtftd_r6_ai_loadouts` (F-14B, air start 1500 m above the start, 600 km/h): 2 enemy Rafale (the saved
  "Rafale C F3 · Custom": Magic / MICA + a pod) and a MiG-29 9.13 with R-73s hunt you, 3 Fw 190 C east.
  Check the Rafale / MiG fire missiles (their loadout is used), the Rafale carry the custom pylons.

## 2f. Template units given another vehicle (new)

Data schema 15 keeps the game templates the scenarios import (`data/templates/`).

**First try (2026-10-09), failed:** the mission carried the templates' whole content (`inline_imports`). The map
loaded, the bombing sites were there, but no enemy and no airfield: the datamine's JSON groups an action used
several times in a trigger (`varSetString` ×4 in `init_rank_settings`), so their order with the other actions is
lost and the rank-based target picking broke. Templates' scripts are therefore never rewritten.

**Now:** the templates stay imported (their scripts run as the game wrote them). The units of a template the
mission imports directly (without imports of its own: `test_flight_unit_template`) are declared by the mission
itself when one of them gets another vehicle, and that import gets `importUnits: no`
(`mission.take_over_units`). Units of nested templates (the bases' Bofors) can't change vehicle.

- [ ] `wtftd_r7_tpl_swap` (F-14B, Afghanistan test flight, the template's targets set by "Vehicles by BR" at 12.7):
  the airfield and the enemies are there as without WTFTD; the air targets are the new aircraft (AV-8B Plus,
  F-2A, F-4E AUP, B-52H, Tu-95…), the ground targets new tanks (Leopard 2, Abrams, Leclerc, T-90M…) and SAM / SPAA.
- [ ] Targets come back after being destroyed (with their new vehicle), the bases and their AA are there.

## 3. Ammunition icons (UI only)

Shell icons (tanks), belt icons (aircraft, helicopters, ships) and flare / chaff icons come from the game's own
table (`aces.vromfs.bin_u/config/gui.blkx` → `bullet_icons`, written to `data/bullet_icons.json`). Data schema
went from 7 to 8: an installed copy rebuilds itself at first launch. Check: the rebuild happens once, the icons
match the hangar's.

- [x] 2026-10-08, Windows: rebuild to schema 8 OK (game v2.59.0.60, 58 s), icons show in the Ammunition step.
- [x] Icons compared with the hangar's (2026-10-08).

## 4. Windows regressions from the macOS work (v0.15.0)

- [x] The app opens in its Edge / Chrome app window and **quits when that window is closed** (Windows still uses
  `proc.wait()`; the close beacon is macOS only). Checked from source (`python -m wtftd`), not the exe.
- [x] Game detection (Steam), **Launch War Thunder**, **Open folder** (UserMissions).
- [x] Standalone (Gaijin launcher): simulated install in `tests/test_platform.py` (found in
  `%LOCALAPPDATA%\WarThunder` without Steam, started with its `launcher.exe`). [ ] A real standalone install.
- [x] Settings: game folder and Oodle placeholders show Windows paths.
- [x] First launch (fresh copy from source, French system): language picker above the logo, translated step
  and time left under the progress bar, no raw log; datamine download + build in 2 min 26 s; a reload does
  not start it again.
- [x] Opening a vehicle: every setup step starts closed.
- [x] Found and fixed on the way: `boot()` could run before `compare.js` / `weapons.js` were loaded
  (`bindCompare` / `bindWeapons is not defined`), and My missions guessed the vehicle from the file name.

## 5. macOS (needs a Mac with the game)

Never run with the game: detection inside `WarThunderLauncher.app`, launch, missions in `UserMissions`
inside the bundle, custom vehicle files (the CDK wiki says the Mac game may reset `content/` at launch).
