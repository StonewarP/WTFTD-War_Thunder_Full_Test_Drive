# Best vehicles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A *Best vehicles* page that ranks the vehicles of a type, mode, BR and play style by the duels they win
against every vehicle they can meet, from new stats the builder derives from the game files.

**Architecture:** The builder adds derived stats to `vehicles.json` (`s`, `su`, record field `bt`) through a new module
`wtftd/duelstats.py`, plus two data fixes in `vehicle_stats`. The browser gets a pure engine `web/duel.js` (no DOM:
styles, duel math, ranking) and a view `web/best.js` (controls, table, matchups) wired into the app like the Challenges
page. `web/stats.js` learns the new stat keys so they are also sortable in the Vehicles list.

**Tech Stack:** Python 3.10+ stdlib (unittest), vanilla JS (no bundler, one global scope), node 22 for JS tests through
`subprocess` (the tests/test_hangar.py pattern), JSON locales in `web/locales/*.json`.

**Spec:** `docs/superpowers/specs/2026-11-17-best-vehicles-design.md` (sections cited as "spec §n"). Weights,
thresholds, gates, candidates and opponents come from spec §4-5 verbatim; this plan does not repeat those tables.

## Global Constraints

- No commits and no pushes: the user commits when they ask. Leave every change in the working tree.
- Never write into the checkout's `data/`, `user/` or `.cache/` from tests or checks; real-data checks build into the
  scratchpad (Task 8).
- Repo texts (code comments, docs, locale strings) use "-", never long dashes; English for code and docs.
- UI strings: static ones in `web/index.html` with `data-i18n`, dynamic ones with `t()`; every new key in all 11
  locales (`en, fr, de, ru, pl, es, pt, it, cs, zh, ja`), non-empty, same `{placeholders}` as English.
- JS: prefix `bv`/`BV` for every new top-level name (one global scope across files); no inline handlers, no inline
  `<script>` (tests/test_safety.py); every game name through `esc()`.
- Data: new `s` keys are written only when the vehicle has the thing; `su` holds stock values that differ (0 when the
  stock vehicle lacks a capability the upgraded one has, `null` when it lacks a measured stat: read as unknown). Bump `SCHEMA` in `wtftd/builder.py` from 40 to 41 (as built: 44, bumped again with the fixes after the real-data checks; 42 and 43 went to the 3D view's commits; 45 with the turn drag `ind`).
- Keep `vehicle_stats(cat, udata, wp, tags, st, ammo)` positional signature (tests/test_costs.py calls it).
- Armor: never output "cannot penetrate" / "immune"; the spec §7 note text is shown on every ground style.
- Test commands: `python -m unittest tests.<module> -v` for one module; full suite
  `python -m unittest discover -s tests -t .` (about 25 s; 1065 tests before this work, all pass).

## Review Focus

1. **Zero and missing values in a duel** (a 0 opponent value in a log ratio, a style whose candidate has none of its
   stats, an empty opponent pool): the page must show *not enough data* or *no opponents*, never `NaN`, `Infinity` or
   a crash. Tests: Task 6 `test_zero_and_empty_never_give_nan`.
2. **Thin windows** (helicopters at BR 7.7 meet 5 helicopters; boats above 4.7 and ships at 2.7 have few opponents):
   ranking still works with 1-3 opponents and with 0. Test: Task 6 `test_small_and_empty_pools`.
3. **Every BR over a whole type** (about 1 450 aircraft or 1 260 ground vehicles, each against about 200 opponents):
   ranking under 300 ms in node. Test: Task 6 `test_every_br_is_fast`.
4. **Stock with partial `su`** (most vehicles have `su` for a few keys only, arrays like `pen` included): stock reads
   `su[k]` when present, else `s[k]`, for scalars and arrays. Tests: Task 5 `test_statat_stock_array`, Task 6
   `test_stock_candidate_against_upgraded_opponents`.
5. **Vehicles that must never be ranked or met** (hidden, rarity 6, mod packages, AI support units, tutorial / race /
   event / missile-test / snowball copies, the launchers of a SAM system): filtered from both pools. Test: Task 6
   `test_pool_leaves_out_unplayable`.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `wtftd/builder.py` | modify | engine-kind `pw`/`tw` and twin-jet thrust (`vehicle_stats`, `card_engine_factor`); `kin`/`heat` fixes; container mass in `build_weapon_catalog`; calls into duelstats from `build_vehicles` and `_build`; record field `bt`; `SCHEMA = 41` (as built, after the real-data checks: `main_gun`, `unguided_launcher`, `bullet_mods`, naval `cal`, the `wl` card floor, the power cap, stock naval speed, `SCHEMA = 44`) |
| `wtftd/duelstats.py` | create | pure functions computing the new stats from data the builder already loaded (no file writes) |
| `wtftd/guidedstats.py` | create | guided weapon stats from the weapons page's index (Task 4), a missile carrier's `gl` and `vel` |
| `wtftd/armament.py` | modify | `build_armament(..., index=None)` fills `index` with its `items` and `by_file` (as built, also `pods`) for the guided-weapon pass; as built, a penetration table without a 0 m value gives its first (the LOSAT's MGM-166) |
| `web/stats.js` | modify | STATS entries for the new keys, flags `dup` / `hint` / `vals`, `statAt` stock arrays, `fmtStat` value labels, `bvRefresh()` call in `setUpgrade` |
| `web/compare.js` | modify | `openCompare(ids)` on a temporary list; skip `dup` stats; per-stat hint |
| `web/duel.js` | create | engine: stat table, styles, duel, pools, windows, ranking (no DOM, no `t()`) |
| `web/best.js` | create | the page: state, controls, table, matchups, notes, bindings |
| `web/index.html` | modify | subtab, `#view-best`, script tags `duel.js`, `best.js` after `hangar.js` |
| `web/app.js` | modify | `MENUS.vehicles` gets `'best'` after `'vehicles'`; `showView` hook; `bindBest()` in boot |
| `web/hangar.js` | modify | `hgSet` calls `bvRefresh()` |
| `web/app.css` | modify | the page's few own classes |
| `web/locales/*.json` (11) | modify | `nav.best`, `bv.*`, `stat.<new>`, value labels |
| `tests/test_power_to_weight.py` | modify | engine-kind and twin-jet cases |
| `tests/test_duel_stats.py` | create | builder stats with made-up inputs (as built: ground stats, the main gun, `kin` / `heat`) |
| `tests/test_air_naval_stats.py` | create | as built: Task 3's aircraft, helicopter and naval stats, the free requirement, stock naval speed, wiring |
| `tests/test_guided_stats.py` | create | as built: Task 4, its wiring and the build's guards |
| `tests/test_best_duel.py` | create | node tests of `web/duel.js` (and `statAt` / `fmtStat`) |
| `tests/test_best_page.py` | create | locales complete for the new keys; page wiring present |
| `README.md` | modify | one line and the feature in the list |

Two independent tracks (no shared file): **Builder** = Tasks 1-4, **Web** = Tasks 5-7. Task 8 needs both.

---

### Task 1: Power or thrust by engine kind, twin-jet thrust

**Files:**
- Modify: `wtftd/builder.py` (`vehicle_stats` air branch around lines 986-1002, `card_engine_factor` around 1110)
- Test: `tests/test_power_to_weight.py`

**Interfaces:**
- Produces: `card_engine_factor(ratio: float, fm: dict, thrust: bool = False) -> int` (thrust=True uses
  `EngineType0.Main.ThrustMax.ThrustMax0` kgf, else `Main.Thrust / 9.81`; mass as today); `vehicle_stats` air output
  has `tw` for jet or rocket engines and `pw` (hp/t) for propeller engines whatever card field the value came from.

- [ ] **Step 1: Write the failing tests** in `tests/test_power_to_weight.py`:
  - `test_prop_card_thrust_field_is_power`: Shop `{"thrustToWeightRatio": 0.35}`, `st = {"lim": {"eng": 1}, "fm": "fm/x"}`,
    a flight model with one `Inline` engine (patch `builder.load` to return it) gives `s["pw"] == 350.0` and no `tw`.
  - `test_rocket_plane_keeps_thrust`: one `Rocket` engine, card `thrustToWeightRatio` 0.4 gives `tw == 0.4`.
  - `test_twin_jet_card_counts_one_engine`: 2 `Jet` engines, `ThrustMax0` 1590, masses empty 4846 + fuel 1500,
    card `thrustToWeightRatio` 0.22 gives `tw == 0.44`.
  - `test_twin_jet_card_counts_both`: 2 `Jet` engines, `ThrustMax0` 1200, masses empty 4000 + fuel 1800, card 0.46
    keeps `tw == 0.46` (F-5A case).
  - `test_old_model_thrust_in_newtons`: no `ThrustMax`, `Main.Thrust` 9319.5 (N), 2 engines, mass 5000, card 0.13
    gives `tw == 0.26`.
- [ ] **Step 2: Run** `python -m unittest tests.test_power_to_weight -v`. Expected: the 5 new tests FAIL.
- [ ] **Step 3: Implement.** In the air branch, load the flight model once (`st["fm"]`), read `engine_kinds(fm)`;
  thrust-powered when a kind is `Jet` or every kind is `Rocket`; take the card value from either field, convert
  (`pw = ratio * 1000` for propeller engines), then apply `card_engine_factor(..., thrust=...)` when `eng > 1`.
  Without a flight model keep today's behaviour.
- [ ] **Step 4: Run** `python -m unittest tests.test_power_to_weight tests.test_costs -v`. Expected: all PASS.

### Task 2: Ground stats and the kin / heat fixes

**Files:**
- Create: `wtftd/duelstats.py`
- Modify: `wtftd/builder.py` (`vehicle_stats` ground branch lines 1003-1035; call site in `build_vehicles` after
  line 1543)
- Test: `tests/test_duel_stats.py`

**Interfaces:**
- Consumes: details `am` groups (`vehicle_ammo`: `trig`, `wi`, `sf`, `opts[{id, x, t, s{pc, v, h}}]`), `sy` and
  `sy.su` (`systems_with_stock`), wpcost entry `v["modifications"]`.
- Produces:
  - `duelstats.stock_shell(mod_id: str, wp_mods: dict) -> bool` (`""` or a free mod: tier 0, no cost, no
    `reqModification`).
  - `duelstats.ground_stats(am: list, sy: dict, wp_mods: dict) -> tuple[dict, dict]` returning `(s_add, su_add)` with
    `pen` `[p500, p1000, p2000]`, `vel`, `dep`, `stab`, `rf`, `th`, `auto`, and `rad` (km, through Task 3's
    `search_radar_km`; write that helper here first if Task 3 is not done yet). As built: `ground_stats(am, sy,
    wp_mods, wc)` reads the main gun's file through the builder's WeaponCache, and also writes the internal `gl` (a
    missile carrier: every round the main gun normally has is a guided missile); `auto` is one barrel's rate (`sf` over
    the group's `tubes`, `emitterGenRange`) of a gun that is no missile carrier; `dep` has one decimal (`sy.el`), never
    below 0.
  - `build_vehicles` also stores `details[vid]["_sm"]` = the free ammo modification ids of that vehicle (for Task 4;
    popped there before details.json is written).
  - `vehicle_stats` ground `kin` / `heat` skip `x` options; `heat` takes gun-launched ATGM penetration (`t` starting
    with `atgm`, flat `pc`).

- [ ] **Step 1: Write the failing tests** (made-up dicts, no files):
  - `test_pen_interpolates_and_skips_x`: main group with a kinetic option `pc [[10,200],[500,180],[1000,160],[2000,120]]`
    and an `x` option at 400 mm gives `pen == [180, 160, 120]`.
  - `test_pen_heat_and_gun_atgm_are_flat`: HEAT `pc [[10,300],[4000,300]]` and an `atgm_tank` option flat 650 give
    `pen == [650, 650, 650]`.
  - `test_vel_is_fastest_unguided_shell`: HEAT-FS `v` 1216 over APBC 914 gives `vel == 1216`; smoke, practice and
    guided missiles never set it.
  - `test_fire_control`: `sy {"el": [-8, 20], "stab": [1, 1, 30], "rf": "laser", "nv": {"g": [["t", 2]]}}` gives
    `dep == 8, stab == 2, rf == 2, th == 1`; `stab [1, 0, 0]` gives 1; `rf "optic"` gives 1.
  - `test_stock_values`: `sy.su {"rf": None, "stab": None}` gives `su["rf"] == 0` and `su["stab"] == 0`; a researched
    shell (`id` with `reqModification` in `wp_mods`) is left out of `su["pen"]`; a free mod (tier 0, no cost) stays.
  - `test_autocannon_flag`: main group `sf` 3.3 gives `auto == 1`; `sf` 0.15 gives no `auto`.
  - `test_kin_heat_fixes`: `vehicle_stats("ground", ...)` with an `x` option of 400 and a regular 200 gives `kin == 200`;
    a gun-launched ATGM 650 with HEAT 550 gives `heat == 650`.
  - As built, also: the other `test_vel_*` cases, `test_depression`, `test_stock_set_a_modification_gives`,
    `test_guided_launcher_flag`; `GroundAmmo` (`tubes`, a set the shared modification table gives under another name),
    `MainGun` (no gunner or first weapon; `build_vehicles`' main weapon), `KinHeat.test_kinetic_missile`.
- [ ] **Step 2: Run** `python -m unittest tests.test_duel_stats -v`. Expected: FAIL (`duelstats` missing).
- [ ] **Step 3: Implement** `ground_stats`, `stock_shell` and the `kin`/`heat` change; in `build_vehicles` merge
  `s_add` into `stats` and `su_add` into `rec["su"]` (create it when needed). Main gun = the group `vehicle_stats`
  already picks (`trig == "gunner0"` or `wi == 1`; as built, `builder.main_gun`: else the largest caliber, never a
  machine gun under 15 mm, and `unguided_launcher` for a gunner's rocket launcher without an ammo set). vel: every
  round of the kept sets in the gun's file (all of a belt), but guided missiles (`t` starting with `atgm`, `sam`) and
  rounds that pierce nothing (`_NO_PEN`); an unguided rocket at its top speed (`maxSpeed`, else `endSpeed`).
- [ ] **Step 4: Run** `python -m unittest tests.test_duel_stats tests.test_costs -v`. Expected: PASS.

### Task 3: Guns, turrets, payload, sensors, countermeasures, naval battery

**Files:**
- Modify: `wtftd/duelstats.py`, `wtftd/builder.py` (`build_weapon_catalog` container branch line 2134; call site
  in `build_vehicles`)
- Test: `tests/test_duel_stats.py`

**Interfaces:**
- Consumes: `WeaponCache.get(blk)` (gun files: `shotFreq`, `bullet[]` with `mass`), `builder._weapons(udata)`, the
  presets list built at `build_vehicles` lines 1479-1494 (`w`, `s`, `req`), the unit's `WeaponSlots` (slot presets
  with `reqModification`), `catalog` (`weapons.json` dict: `c`, `m`, `pod`), `sy` (`cm`, `se`), `st["lim"]`.
- Produces:
  - `duelstats.gun_burst(weapons: list, wc, forward: set[str]) -> float` (kg/s: shots/s, Weapon override else gun
    file `shotFreq`, times mean bullet mass of the default belt; skips `dummy`).
  - `duelstats.preset_is_stock(preset: dict, udata: dict) -> bool` (no `req`, and no slot preset it uses has
    `reqModification`).
  - `duelstats.search_radar_km(sy: dict) -> float | None` (longest radar / radar_irst entry whose role is search,
    `ro` `s` or `st`; km, 1 decimal); used for `rad` of every type.
  - `duelstats.air_stats(cat: str, udata: dict, wc, presets: list, catalog: dict, sy: dict, lim: dict) -> tuple[dict, dict]`
    with `fg`, `vne` (air), `pay`, `cm`, `rwr`, `rad`, `def` (air), `th` (heli).
  - `duelstats.naval_stats(udata: dict, wc, sy: dict) -> dict` with `fm` (kg/min, trigger group `primary`) and `rad`.
  - `aab` for SPAA (`k` SPAA): `gun_burst` over every gun weapon of the vehicle, added to the ground stats.
  - `build_vehicles` stores `details[vid]["_sp"]` = the ids of the stock presets (`preset_is_stock`) for Task 4.
  - Catalog container entries get `m = container mass + pod x inner mass`.
- As built (departures from the above, same results unless said):
  - `gun_burst(weapons, wc)` has no `forward` argument: callers filter (forward triggers without `schraegeMusikAngle`;
    trigger group `primary`).
  - `air_stats(..., lim, mods=())`, `spaa_stats(udata, wc, mods=())` and `naval_stats(udata, wc, sy, mods=())` take the
    modifications the vehicle can research and all return `(s, su)`: `fitted_sets` adds the fitted weapons of each
    modification that replaces them (`effects.commonWeapons`), counted upgraded only (it changes `fg`, `cm`, `fm`).
  - Fitted countermeasures come from the unit's weapons (those sets), not from `sy.cm`; a preset's weapons are read from
    its file through `wc` (pods and racks keep their masses), not from the composition `w`.
  - Aircraft `rad` is the range against aircraft (`air_range`, from the radar's file through `wc`); ground and naval
    keep `search_radar_km`.
  - Tests in `tests/test_air_naval_stats.py` (lane split), with a `build_vehicles` wiring test.
  - After the real-data checks: `preset_is_stock(preset, udata, wp_mods=None)` counts a requirement `stock_shell`
    calls free as met (a ship's `ship_torpedoes`), and `air_stats(..., mods=(), wp_mods=None)` passes it on;
    helicopters' forward guns include `gunner1` and `gunner2`, and `air_stats` writes their internal `rkt` (`pay`
    without the guided weapons); `naval_stats` also writes `fa` (every gun of a fitted set). In `builder.py`:
    naval `cal` from trigger group `primary` (`vehicle_stats`), stock naval speed (`stock_factors` "S" from
    `mulMaxSpeed`, a boat / ship branch in `stock_stats`), and the duel stats and the private lists in a try of their
    own in `build_vehicles` (a failure loses those stats, not the vehicle). Tests: `Naval` (`fa`, `cal`, free
    requirement, stock speed), `Helicopter` (flexible forward guns, rockets and bombs).

- [ ] **Step 1: Write the failing tests** (a fake `wc` whose `get` returns gun dicts):
  - `test_gun_burst_forward_only`: weapons `cannon` (shotFreq 10, bullets 0.1 and 0.2 kg) and `gunner0` (shotFreq 20,
    0.05 kg): aircraft `fg == 1.5`; helicopter (gunner0 forward) `fg == 2.5`.
  - `test_weapon_shotfreq_override`: Weapon block `shotFreq` 5 beats the file's 10.
  - `test_gun_pod_best_preset`: built-in 1.5 plus a preset with an `external` `additional gun` pod (shotFreq 10,
    0.1 kg) gives `fg == 2.5`; stock (pod preset needs a mod) `su["fg"] == 1.5`.
  - `test_defensive_turrets`: triggers gunner0, gunner1, gunner1 on an aircraft give `def == 2`.
  - `test_payload_with_pods`: preset `[["bomb_250", 2], ["rocket_pod", 2]]`, catalog bomb `m` 250, pod
    `m` 157.8 gives `pay == 815.6`; a slot preset with `reqModification` makes that preset not stock.
  - `test_countermeasures_with_pods`: a fitted launcher of 60 (a `countermeasures` Weapon) plus a preset with a
    `countermeasures` pod of 30 gives `cm == 90`.
  - `test_sensors`: `sy.se` radar `{"r": 54000, "ro": "st"}` gives `rad == 54`; a radar with `ro` `rf` only gives no
    `rad`; an `rwr` entry gives `rwr == 1`.
  - `test_vne`: `lim {"v": 870}` gives `vne == 870`; swept `lim.sw` uses `lim.v` as given (already swept-back).
  - `test_heli_thermal`: `sy.nv {"s": [["t", 2]]}` gives `th == 1` on a helicopter.
  - `test_naval_primary_battery`: two `primary` guns (shotFreq 0.2, shell 25 kg) and one `machinegun` give
    `fm == 600.0`; a ship radar `{"r": 30000, "ro": "s"}` gives `rad == 30`.
  - `test_spaa_burst`: an SPAA with 2 barrels of shotFreq 10 and 0.2 kg shells gives `aab == 4.0`.
  - `test_container_mass`: catalog build on a container with `bullets` 19, inner rocket 6.2 kg, own mass 40 gives
    `m == 157.8`.
- [ ] **Step 2: Run** `python -m unittest tests.test_duel_stats -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the functions and call `air_stats` (air, heli) and `naval_stats` (boat, ship) in
  `build_vehicles` next to `ground_stats`. `fg` is the best preset: fitted forward guns plus that preset's forward
  guns, pods included (a rule "guns every preset repeats count as built-in" gives 0 for the Mirage IIIC, F-104S and
  MiG-21 PFM).
- [ ] **Step 4: Run** `python -m unittest tests.test_duel_stats tests.test_costs tests.test_power_to_weight -v`.
  Expected: PASS.

### Task 4: Guided weapons, ground-battle BR, wiring and schema

**Files:**
- Create: `wtftd/guidedstats.py`
- Modify: `wtftd/duelstats.py` (`ground_battle_br`, at the end), `wtftd/armament.py` (`build_armament`'s `index`),
  `wtftd/builder.py` (`_build` wiring; in `build_vehicles`: `rec["bt"]`, and details `_gw` / `_ml` for ground vehicles;
  `SCHEMA`)
- Test: `tests/test_guided_stats.py`

**Interfaces:**
- Consumes: armament `items` `{id: {c, g, rng, lk, aa, ccm, pen, act, ff, ins, v, ...}}`, details `pr` / `am` per
  vehicle, wpcost entry, and the private details keys `build_vehicles` leaves:
  - `_sp`: stock preset ids (Task 3). When it is missing, every preset is stock.
  - `_sm`: free ammo mods (Task 2).
  - Ground vehicles only: `_gw` = `[[[file key, rounds], ...], ...]`, launchers without an ammo set, one list per
    fitted set: the vehicle's own first, then each replacing modification's.
  - Ground vehicles only: `_ml` = `{ammo mod: maxToRespawn}`.
- Produces:
  - `armament.build_armament(lang, vehicles, progress=None, index=None)` fills `items` (`{id: item}`, before
    de-duplication), `by_file` (`{file key: [that file's own item dicts]}`, with `ship: 1` when a seeker's
    `targetRadiusMin` is 10 m or more) and `pods` (`{container key: (inner file key, rounds)}`); return value unchanged.
  - `guidedstats.guided_stats(vehicles, details, items, by_file, pods=None) -> None` writes the 12 keys `ir`, `irq`,
    `rm`, `rmq`, `rmr`, `atg`, `atr`, `atp`, `atq`, `sam`, `tor`, `torr` into `s` / `su`, a missile carrier's `vel`
    (its fastest missile, when `ground_stats` gave none) and `gl` (when the main weapon is a launcher `am` leaves out:
    the M113A1 (TOW)), and pops `_sp`, `_sm`, `_gw` and `_ml`, also from a vehicle whose data fails (logged, no guided
    key). That is why `_build` calls it before writing details.json.
  - `duelstats.ground_battle_br(wp_entry: dict, br: list) -> list | None` (`bt`: `[br[0], TankHistorical or br[1],
    TankSimulation or br[2]]`, `None` when equal to `br`).

- [ ] **Step 1: Write the failing tests:**
  - `test_aam_counts_and_kinds`: presets with 4 IR items (`aa` > 0, `ccm` 0.5) and 2 `arh` radar items (`rng` 50000)
    give `ir == 4, irq == 3, rm == 2, rmq == 2, rmr == 50`.
  - `test_guided_ground_weapons`: an ATGM (`rng` 8000, `pen` 1200, `g` laser), an AGM `g` `arm` (`rng` 50000) and an
    anti-ship AGM-84D give `atg` counting only the ATGM, `atr == 8000`, `atp == 1200`, `atq == 1`; an IR AGM with
    `rng` 26400 gives `atr == 10000` and `atq == 2`; a guided bomb without `rng` counts 8000.
  - `test_sam_reach`: an IR SAM (`rng` 10000, `lk` 5500) gives `sam == 5500`; a command-guided SAM `rng` 8000 gives
    8000. As built, also: Stinger (`lk` 11000, `aa` 5500) gives 5500; Python-5 (`rng` 8000, `aa` 9000) gives 8000;
    IRIS-T SLM (`ins`, `rng` 40000) gives 40000; 9M311 gives 8000.
  - `test_torpedoes`: preset `[["mk15", 10]]`, item `rng` 5500 gives `tor == 10, torr == 5500`.
  - `test_ground_launcher_and_gun_atgm`: a separate launcher and a gun-launched ATGM both count in `atg` / `atr`.
  - `test_ground_battle_br`: `{"economicRankTankHistorical": 26}` with `br [10.7, 10.3, 10.7]` gives
    `[10.7, 9.7, 10.7]`; no Tank keys gives `None`.
  - As built, also: in `test_aam_counts_and_kinds` the Sidearm and the AA.20 are not `rm`; in
    `test_guided_ground_weapons` the Penguin is not counted, 12 LAU-131 pods of 7 give 84, the SS-11 (no pen) writes
    no `atp` and a Malyutka counts; `test_gun_missiles_per_spawn`, `test_dual_purpose_missile`,
    `test_launchers_without_ammo_sets`, `test_modification_launchers`, `test_stock_values`,
    `test_missile_carrier_speed`, `test_missile_launcher_am_leaves_out`; `Wiring` (`test_armament_index`,
    `test_build_vehicles_gives_what_they_read`, `test_the_build_writes_them_and_drops_the_stock_lists`); `Guards` (a
    vehicle whose guided or duel stats fail keeps its record).
- [ ] **Step 2: Run** `python -m unittest tests.test_guided_stats -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** A weapon key goes through `pods` first, then `by_file[key]`, else the key without
  `(_default|_\d+)$` (spec §3 fix 3; real data: 5714 of 5714 guided preset keys map, 5680 directly, 34 through pods);
  ground ammo sets are looked up in `items` by bullet name. Stock through `_sp` (`preset_is_stock`, Task 3) and `_sm`
  (`stock_shell`, Task 2). In `_build`: `idx = {}`, `build_armament(lang, vehicles, progress, idx)`, then
  `guidedstats.guided_stats(vehicles, details, idx["items"], idx["by_file"], idx["pods"])` before `vehicles.json` and
  details.json are written; set `rec["bt"]` in `build_vehicles` for aircraft; `SCHEMA = 41`.
- [ ] **Step 4: Run** `python -m unittest discover -s tests -t .`. Expected: all PASS (1065 + new).

### Task 5: The new stats in the app (stats.js, compare.js, labels)

**Files:**
- Modify: `web/stats.js`, `web/compare.js`, `web/locales/*.json` (11)
- Test: `tests/test_best_duel.py` (statAt / fmtStat part), `tests/test_best_page.py` (labels)

**Interfaces:**
- Produces:
  - STATS entries (key: cats, unit, better, digits) - `fg` air+heli kg/s +1 d1; `vne` air km/h +1 `dup`; `pay`
    air+heli kg +1; `ir` air+heli +1; `irq` air+heli +1 `vals`; `rm` air +1; `rmq` air +1 `vals`; `rmr` air km +1;
    `rad` all km +1 `dup`; `cm` air+heli +1 `dup`; `rwr` air+heli +1 `dup` `vals`; `def` air +1; `atg` air+heli+ground
    +1; `atr` air+heli+ground m +1; `atp` heli+ground mm +1; `atq` air+heli+ground +1 `vals`; `pen` ground mm +1
    `triple` `hint: 'stat.penHint'`; `vel` ground m/s +1; `dep` ground ° +1 `dup`; `stab` ground +1 `dup` `vals`; `rf`
    ground +1 `dup` `vals`; `th` ground+heli +1 `dup` `vals`; `sam` ground m +1; `aab` ground kg/s +1 d1; `fm` naval
    kg/min +1; `tor` naval +1; `torr` naval m +1. As built, after the real-data checks: `fa` naval kg/min +1 (next to
    `fm`, `stat.fa` "All guns firepower"); `dep` d1 (`fmtStat` drops a trailing .0: 4.5°, 10°); `stat.vel` the game's own
    term (menu.csv `bullet_properties/speed`: "Muzzle velocity"). `gl`, `auto` and `rkt` are internal: no entry.
  - Flags: `dup` = not a panel tile (`statsBlockHTML`) nor a compare row (compare.js STATS loop), still sortable and
    filterable; `hint` = the tooltip key (default for `triple` stays `stat.armHint`); `vals` = `fmtStat` shows
    `t('stat.<k>.<value>')` instead of a number.
  - `statAt(v, k)`: with `!S.upg`, an array `v.su[k]` is returned for an array stat.
  - `openCompare(ids?: string[])`: when `ids` is given the dialog shows them and `S.compare` / the tray stay as they
    were; `renderCompareTable()` uses that list while the dialog is open (also when `setUpgrade` re-renders it).
  - `setUpgrade` ends with `if (typeof bvRefresh === 'function') bvRefresh();`.
  - Locale keys: `stat.<each new key>`, `stat.penHint`, `stat.irq.1|2|3`, `stat.rmq.1|2`, `stat.rwr.1`, `stat.atq.1|2`,
    `stat.stab.1|2`, `stat.rf.1|2`, `stat.th.1`.

- [ ] **Step 1: Write the failing tests:**
  - `test_statat_stock_array` (node, stats.js loaded with the stubs of tests/test_hangar.py plus `document`, `S`, `t`,
    `I18N`): `S.upg = false`, `v = {s: {pen: [200, 180, 150]}, su: {pen: [150, 140, 100]}}` gives `[150, 140, 100]`;
    without `su.pen` gives `[200, 180, 150]`.
  - `test_fmtstat_value_labels`: `fmtStat('rf', 2)` returns `t('stat.rf.2')` (the stub `t` returns the key).
  - `test_new_stat_labels_in_every_locale` (`tests/test_best_page.py`): every STATS key of the list above has
    `stat.<k>` non-empty in the 11 locales; every `vals` stat has its value keys.
  - `test_compare_temporary_list` (node, compare.js): with `S.compare = ['a']`, `openCompare(['x', 'y'])` leaves
    `S.compare` equal to `['a']` (stub the dialog and loaders).
- [ ] **Step 2: Run** `python -m unittest tests.test_best_duel tests.test_best_page -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the entries, flags, `statAt` branch, `fmtStat` value labels, compare changes, labels in
  the 11 locales (translated, not English copies).
- [ ] **Step 4: Run** `python -m unittest tests.test_best_duel tests.test_best_page tests.test_compare tests.test_safety -v`.
  Expected: PASS.

### Task 6: The duel engine (web/duel.js)

**Files:**
- Create: `web/duel.js`
- Test: `tests/test_best_duel.py`

**Interfaces:**
- Consumes: vehicle records (`id, c, n, r, br, bt, k, ro, s, su, ra, h, mod`).
- Produces (all top-level, no DOM, no `t()`):
  - `BV_STATS`: `{key: {dir, kind: 'abs'|'rel', e, d, cap}}` = spec §5 default thresholds (`cap: true` for the
    capability stats of spec §4); pseudo keys `pwr`, `pen500`, `pen1000`, `pen2000`, `kill1000`, `kill2000`.
  - `BV_TYPES = {air: ['air'], heli: ['heli'], ground: ['ground'], naval: ['boat', 'ship']}`.
  - `BV_STYLES`: `{air: [...], heli: [...], ground: [...], naval: [...]}`; each style
    `{id, cand(v) -> bool, brField?: 'bt', foes: [{is(v) -> bool, terms: {key: weight}, gates: ['refuse'|'above'|'outgun'], range?: m, brField?: 'bt'}], mission?: {key: weight}, m?: number, modes: ['ab','rb','sb'], notes: ['armor'|'abApprox'|...]}`
    (`brField: 'bt'` reads the aircraft's ground-battle BR, falling back to `br`: the candidates of `cas`, the aircraft
    opponents of `cas` and `spaa`)
    with ids `turn, bnz, energy, hunter, cas, bomber, missile` / `hatgm, hrocket, hair` /
    `brawl, snipe, flank, ambush, spaa` / `nbrawl, ntorp, ndd, nrange` and the content of spec §5.
  - `bvVal(v, key, stock) -> number|null` (capability absent = 0; measured absent = null; `stock` reads `su` first).
  - `bvTerm(key, a, b, pair) -> number|null` (`pair` = 'prop'|'jet'|'mixed' for `spd` thresholds).
  - `bvDuel(A, B, foe, ctx) -> {v: 'adv'|'even'|'dis'|'na', D, terms: [{k, w, t, a, b}], gate: string|null}` where
    `ctx = {mode: 0|1|2, stock: bool}`; mode factors of spec §4; armor terms only when both BRs < 8.7.
  - `bvSteps(a, b)`, `bvInWindow(br, other) -> bool` (|steps| <= 3), `bvBr(v, mode, field) -> number|null`.
  - `bvPool(vehicles, {removed}) -> vehicle[]` (filters of spec §2; `removed` false drops `ra` 5 from candidates only).
  - `bvRank({vehicles, type, style, mode, br, stock, onlyStyle}) -> [{v, score, net, mission, w, e, l, na, meanD, n}]`
    (`br` null = every BR); `bvMatchups(row, ctx) -> [{o, res}]` computed on demand for one row.
- As built, after the real-data checks: a style's `cand(v, stock)` (only `cas` reads `stock`; bvRank passes it for the
  rows and the mission population, best.js's BR list `!S.upg`); a foe may carry `need: {term: other term}` (compared
  only when either side has the other > 0), `th` (overrides of `BV_STATS` for its terms: `BV_WIDE`'s reach bands
  500 / 2000 m, Torpedo attack's `disp` direction -1), `reach: [A's, B's]` and `turret`; notes add `navalArmor`; `bvRank`'s `net` is
  the mean of each foe group's; `bvSides` leaves out a missile carrier's (`s.gl`) `cal` and an `auto` gun's `rel`;
  `BV_UNPLAYED` adds `snowball` and `_launcher$`; `BV_STATS` adds `fa` and `rkt`. Tests in `tests/test_best_duel.py`
  (`DuelEngine`, `BrList`).

- [ ] **Step 1: Write the failing tests** (node harness running `web/duel.js` alone, results as JSON):
  - `test_terms_abs_rel_and_direction`: `bvTerm('turn', 18, 20.5)` > 0 (lower better); inside the even band gives 0;
    `bvTerm('fg', 3, 2)` equals `-bvTerm('fg', 2, 3)` (log ratio is symmetric); decisive gives exactly 1.
  - `test_capabilities`: `rad` 0 vs 0 gives `null` (skipped); 0 vs 54 gives -1.
  - `test_coverage_and_not_enough_data`: a style whose measured stats are unknown on one side for more than 40% of the
    weight gives `v == 'na'`.
  - `test_verdict_thresholds`: D 0.2 gives `adv`, 0.19 gives `even`, -0.2 gives `dis`.
  - `test_gates`: turn fight against a foe 5% faster and 16% better climber is at best `even` with `gate == 'refuse'`;
    boom and zoom against a faster, better-climbing foe is `dis` with `gate == 'above'`; a brawler with 200 mm against
    450 mm at 500 m is `dis` with `gate == 'outgun'`.
  - `test_armor_cut_at_8_7`: the `front` term is used at 8.3 vs 8.3 and absent when either vehicle is at 8.7.
  - `test_pair_terms_reach_side_kill`: helicopter `atr` 8000 against an SPAA with `sam` 5500 gives a positive `reach`
    term (2500 m: decisive at 1500); against a gun SPAA (3000 m) with `atr` 2500 gives a negative one; `side` with
    pen500 160 against side 80 is +1; `kill1000` of a missile carrier with gun pen 75 and `atp` 500 at `atr` 4000 is 500.
  - `test_cas_uses_ground_battle_br`: a `cas` candidate with `br` RB 10.3 and `bt` RB 9.7 is ranked in the 9.7 window.
  - `test_window`: at 6.7 the window holds 5.7 and 7.7 and not 5.3 or 8.0.
  - `test_pool_leaves_out_unplayable`: `h`, `ra` 6, `mod`, ids `x_killstreak`, `nt_x`, `uav_x`, `ucav_x`,
    `germ_panther_II_tutorial`, `ussr_t_80u_race`, `f_4e_event`, `f_16c_block_50_missile_test` are not in `bvPool`.
  - `test_mission_percentile_and_score`: three candidates with `pay` 100, 200, 200 give percentiles 1/6, 2/3, 2/3
    (ties half) and `score = (1 - m) * net + m * mission`.
  - `test_rank_order_and_ties`: higher score first, equal score ordered by higher `meanD`.
  - `test_stock_candidate_against_upgraded_opponents`: with `stock` true the candidate reads `su`, the opponent `s`.
  - `test_zero_and_empty_never_give_nan`: an opponent with `fg` 0 and `pay` 0, a candidate with no stats at all, a
    style with no opponents: every number in the output is finite and the verdicts are `na` where nothing compares.
  - `test_small_and_empty_pools`: a window with 1 opponent ranks; with 0 opponents every row has `n == 0`, `score`
    from the mission part only (or 0 when there is none).
  - `test_every_br_is_fast`: 1 500 generated aircraft over 43 BRs, `bvRank` with `br: null` finishes under 300 ms.
- [ ] **Step 2: Run** `python -m unittest tests.test_best_duel -v`. Expected: FAIL (`duel.js` missing).
- [ ] **Step 3: Implement** `web/duel.js` from spec §4-5. Build each vehicle's value vector once per rank call; compute
  terms and reasons only when needed (`bvMatchups`).
- [ ] **Step 4: Run** `python -m unittest tests.test_best_duel -v`. Expected: PASS.

### Task 7: The page (web/best.js and wiring)

**Files:**
- Create: `web/best.js`
- Modify: `web/index.html`, `web/app.js`, `web/hangar.js`, `web/app.css`, `web/locales/*.json` (11)
- Test: `tests/test_best_page.py`

**Interfaces:**
- Consumes: Task 6 (`BV_STYLES`, `bvRank`, `bvMatchups`, `bvPool`), Task 5 (`STATS`, `fmtStat`, `statLabel`,
  `upgSwitchHTML`, `openCompare(ids)`), app helpers (`t`, `esc`, `$`, `$$`, `store`, `flagHTML`, `unitImgTag`,
  `ROMAN`, `className`, `fmtBR`, `I18N`, `showView`, `openVehicle`, `hgTestDrive`, `HG.owned`, `HG.loading`).
- Produces: `bindBest()`, `openBestView()`, `bvRender()`, `bvRefresh()` (re-renders only when `#view-best` is
  visible); state `BV` saved under `store` key `bv`; locale keys `nav.best` and `bv.*`.

- [ ] **Step 1: Write the failing tests** in `tests/test_best_page.py`:
  - `test_page_is_wired`: index.html has `data-view="best"` right after `data-view="vehicles"`, `id="view-best"`,
    `<script src="duel.js">` and `<script src="best.js">` after `hangar.js`; app.js `MENUS.vehicles` lists `'best'`
    after `'vehicles'`, calls `bindBest()` and `openBestView()`; hangar.js `hgSet` calls `bvRefresh`.
  - `test_bv_keys_in_every_locale`: every `'bv.<x>'` literal in best.js (regex like tests/test_compare.py) exists in
    en.json and, with the same placeholders, non-empty in the 11 locales; one `bv.style.<id>` and `bv.styleh.<id>` per
    style id of duel.js.
  - `test_armor_note_text`: `bv.armor` in en.json mentions BR 8.7 and the Leopard 2A6 75 mm example; best.js shows it
    for every ground style.
- [ ] **Step 2: Run** `python -m unittest tests.test_best_page -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the page per spec §6: controls bar (type, mode with SB disabled for naval, BR select plus
  *Every BR*, style with its one-line description, rank chips, nation chips, owned / removed / only-style switches,
  `upgSwitchHTML()`), notes (armor, SB, AB approximation for `cas` and `spaa`, stats-only), result table (first 100,
  *Show more*, sortable score / BR / rank / name), row matchups grouped adv / even / dis / na with reasons as chips
  (`chip info` better, `chip warn` worse; armor reasons end with `*` carrying `bv.armor` as title), actions open /
  compare with an opponent (`openCompare([v.id, o.id])`) / test drive. Await `HG.loading` before using `HG.owned`.
- [ ] **Step 4: Run** `python -m unittest tests.test_best_page tests.test_safety tests.test_compare tests.test_hangar -v`.
  Expected: PASS.

### Task 8: Real data, whole suite, the page in the app

**Files:** none in the repo (scratchpad only).

- [ ] **Step 1: Build the data into the scratchpad** (the checkout's `data/` is not touched):
  ```bash
  python -c "import sys; sys.path.insert(0, r'C:\Users\pierr\Downloads\WTFTD'); from pathlib import Path; from wtftd import builder, armament; out = Path(r'<scratchpad>\bvdata'); out.mkdir(exist_ok=True); builder.DM = builder.GAMEFILES; builder.DATA = armament.DATA = out; builder._build(None, 'game', history=False)"
  ```
  Expected: `<scratchpad>\bvdata\vehicles.json` with `meta.json` schema 41 (as built: 44).
- [ ] **Step 2: Spot-check stats** with `python -I` on that vehicles.json: `fg` Bf 109 F-4 3.1 (stock 1.7), Fw 190 A-8
  about 6.2; `tw` Meteor F.8 about 0.44, F-5A 0.46; `pw` B-17G about 240; `kin` T-34 (1941) 99 (`pen` [87, 75, 57]:
  its BR-350SP set comes through the shared modification table); `fm` Fletcher about 2700; `pay` B-17G about 5770; `sam`
  and `rad` on the 2S6; `bt` on the Su-25.
- [ ] **Step 3: Rankings** with node loading `web/duel.js` and that vehicles.json, RB: turn fighting 3.7 top 15 has
  Spitfires / Zeros / Yaks; boom and zoom 5.0 top 6 has Fw 190 Ds; bomber hunting 4.0 favours heavy-cannon fighters;
  sniper 6.7 favours high-velocity guns; brawler 5.7 and 6.7 have no armoured car or IFV; every style of every type
  returns finite scores. Write down any implausible top 10.
- [ ] **Step 4: Full suite** `python -m unittest discover -s tests -t .`. Expected: all PASS.
- [ ] **Step 5: The page in the browser** from a scratchpad copy (memory: preview writes user data): copy `wtftd/`,
  `web/` and `bvdata` as `data/` into `<scratchpad>\bvapp`, run it through a `.claude/launch.json` entry on port 8781
  (`py -3.14 -c "import sys, runpy; sys.path.insert(0, r'<scratchpad>\bvapp'); sys.argv = ['wtftd', '--no-window', '--port', '8781']; runpy.run_module('wtftd', run_name='__main__')"`),
  open *Best vehicles*: each type and style renders, a row opens its matchups, the armor note shows on ground styles,
  compare opens on two vehicles and the tray is unchanged, no console error; screenshots for the user. Remove the
  launch entry afterwards.

### Task 9: README and wiki text

**Files:**
- Modify: `README.md` (one line in the feature list, linking the wiki page)
- Create: `<scratchpad>\wiki\Best-vehicles.md` (the wiki is its own repo; publishing it waits for the user)

- [ ] **Step 1:** Add the README line; write the wiki page (Where / How to use / How it works / Limits, the armor
  limit text of spec §7, no long dashes).
- [ ] **Step 2: Run** `python -m unittest discover -s tests -t .`. Expected: PASS.
