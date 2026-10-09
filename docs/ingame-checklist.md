# In-game checklist

What can only be checked with War Thunder installed (Windows). Written on 2026-10-08 after work done on a
Mac without the game. Tick each line, note what you see, then fix or remove the item.

Setup: `python -m wtftd` from this repository (or the exe built from `main`), custom vehicles on (default).
After a mission is created: start War Thunder → **Single missions → User missions**.
Test missions are named here by their title in that list (file name in brackets); from 2026-10-09 on, the test
to do is also written in the mission's description, shown under it in the game.

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

- [x] `wtftd_r7_tpl_swap` (F-14B, Afghanistan test flight, the template's targets set by "Vehicles by BR" at 12.7):
  the airfield and the enemies are there; the targets are the new vehicles; they come back after being destroyed
  (2026-10-09). Found: a dirt airfield (the file's `target_rank_index` 1: the hangar passes your rank, a user mission
  doesn't) and SAM "AA" that were only their battery's radar (`*_fcs`, unarmed: the research tree's slot).
- [x] Same mission, regenerated: high-rank airfield and target zones (`target_rank_index` follows your vehicle);
  SAM launchers are there (2026-10-09). They did not fire: the template's targets are `hold_fire` / `dont_aim`, and
  its scripts set the aircraft `cannotShoot` each time they spawn them.
- [x] Same mission, regenerated with Vehicles by BR → Fire: Attacks (every target `attack: fire_at_will`; WTFTD's
  `wtftd_attack` trigger sets `attack_type: fire_at_will, cannotShoot: no` on them every 3 s): the SAM launchers
  (with their radar 30 m away), tanks, SPAA and aircraft shoot at you, also after they respawn.
  First run (2026-10-09): the HQ-11 (a SAM with its own radar) fires; shot down before seeing the rest.
  Invulnerable run (2026-10-09): HQ-11, Spyder and tanks fire; the SAM batteries' launchers don't (even with their
  radar 30 m away: dropped, Vehicles by BR now picks vehicles that fire on their own), the aircraft don't.
- [x] Regenerated (invulnerable): HQ-11, Spyder and tanks fire (no Pantsir seen); the template's aircraft, told
  to hunt you every 10 s (`wtftd_hunt`), neither came at you nor fired (2026-10-09). Same `unitAttackTarget` as
  Gaijin's missions. Open: their scripts' route wins, or AI aircraft leave a player alone while the invulnerable
  cheat's `invulnerabilityTimer` (spawn protection) is on.
- [x] **WTFTD r7b: aircraft hunting you (not invulnerable)** (`wtftd_r7_air_hunt`, 2026-10-09): no MiG-29 seen,
  shot down by the SAM. (r7b and r7c: the MiG-29 were written by hand as `mig-29_9_13`, not a game unit (it is
  `mig_29_9_13`): the game dropped them; the editor only offers real ids.) The 2 MiG-29 were in the mission ~7 km from the real start (`spawn_area01`); their hunt order
  was only given at mission start, before the templates' scripts spawn you: lost. Now every hunt order (added and
  scenario units too) is given again every 10 s (`wtftd_hunt`).
- [x] **WTFTD r7c: aircraft hunting you, ground passive** (`wtftd_r7_air_hunt`, 2026-10-09): a template F-4E
  came at the player and shot them down: Hunts me works for aircraft once the order is repeated (every 10 s).
  The earlier invulnerable run already repeated it for the template's aircraft and none attacked: the invulnerable
  cheat (`isImmortal` + `invulnerabilityTimer`, spawn protection) most likely makes AI aircraft leave you alone.
  Seen live (game web UI, port 8111): shot down again and again by F-4E AUP and F-2A (template aircraft), and by
  HQ-11 / Spyder standing in for template targets that Gaijin's template already sets to fire at will.
- [x] **WTFTD r7d: 2 MiG-29 + target aircraft hunt you, ground silent** (`wtftd_r7_air_hunt`, 2026-10-09, watched
  live on the game's web UI, port 8111): "MiG-29 shot down StonewarP"; after the respawn the 2 MiG-29 closed from
  3.6 to 1.3 km in 15 s, 2 target fighters (F-4E AUP / F-2A) from 19 to 16 km; the 2 AV-8B (attack aircraft) stayed
  7-10 km away. Hunts me works for added and template aircraft.

## 2g. Invulnerable without spawn protection, unbreakable airframe (new)

Invulnerable no longer sets `invulnerabilityTimer` (the spawn protection: AI aircraft left the player alone, 2f),
only `isImmortal` (+ the custom vehicle's hit points ×1000). A crash into the ground still kills you (a revive
after it was dropped at the user's request). New cheat **Unbreakable airframe** (aircraft / helicopters, custom vehicles): the
flight model's breaking limits raised (`Vne`, `VneMach`, `Strength/VNE` and `MNE` → 100000 km/h / Mach 100; `CritOverload`,
`WingCritOverload` ×100; gear, flaps, airbrake, canopy breaking speeds → 100000).

- [x] First r8 with thrust ×20 (2026-10-09): no more power. Jets take their maximum thrust from the flight model's
  `ThrustMax` table (`ThrustMax0` × coefficients by altitude / speed), not `Main/Thrust`, which was all the Thrust
  mod changed: it never worked. Fixed: `ThrustMax0` of every engine type scaled too.
- [x] r8 with the thrust fixed (2026-10-09, live: Mach 3.49, 2806 km/h IAS at 6600 m): power OK, but the wings
  broke with speed: each wing's `Strength` block also has `MNE` (Mach limit, 0.96 on the F-14B), not raised.
  Fixed (`MNE`, and `VneHeli`, `chuteRipSpeed`).
- [x] **WTFTD r8b: invulnerable, unbreakable airframe (Mach limit too), hunted** (`wtftd_r8_invulnerable`): past
  Mach 1 up to Mach 3+ and pulling hard, the wings stay on; the aircraft come at you and fire, you don't die. All good (2026-10-09).
- [x] (superseded by r8b) **WTFTD r8: invulnerable, unbreakable airframe, hunted** (`wtftd_r8_invulnerable`, F-14B, Afghanistan; the
  test is in its description): the MiG-29 and the target fighters still come at you and fire, you don't die;
  past the speed limit (thrust ×20 to get there fast) and pulling hard the wings stay on, gear and flaps don't
  break.

## 2h. Super mobility cheat (new)

Custom vehicles. Ground vehicles: `engine/horsePowers` ×4, `mechanics/mainGearRatio` ÷2 (top speed ×2),
`mechanics/maxBrakeForce` ×3. Aircraft: jets `ThrustMax0` ×3, piston engines `Main/Power` and the compressor's
`Power<n>` / `PowerConstRPM<n>` / `PowerAtCeiling<n>` ×3; `Mass/EmptyMass` ×0.6. A value set under Modifications
wins. (The ground modifications themselves had never been checked in game.) Aircraft handling too (`cdk._handling_overrides`):
`MomentOfInertia` ×0.4, `Areas/Aileron|Elevator|Rudder` ×1.5, `*EffectiveSpeed` and `*MaxDv` ×2, the wing's
`ClCritHigh` / `ClCritLow` ×1.3 (NoFlaps / FullFlaps, WingPlane* / FlapsPolar*), every `CdMin` ×0.5.

- [x] **WTFTD r9a: super mobility, T-72A** (`wtftd_r9_mobility_tank`, tank test drive): much faster acceleration,
  top speed about 120 km/h instead of 60, still turns and brakes well.
- [x] **WTFTD r9b: super mobility, Bf 109 F-4** (`wtftd_r9_mobility_air`, Afghanistan test flight): roll, pitch, turn
  time, acceleration and climb far better (3510 hp instead of 1170, 40 % lighter, half the drag); still flyable;
  the engine runs normally.
- [x] **WTFTD r9c: super mobility + unbreakable airframe, F-14B** (`wtftd_r9_mobility_jet`): roll, pitch, turn time
  and acceleration far better than a normal F-14B; still flyable; the wings stay on in hard turns.
  r9a, r9b, r9c all good (2026-10-09).

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
