# Best vehicles - design

Date: 2026-11-17, updated 2026-11-18 with the fixes of the real-data checks (calls 15 on). Status: the logic and the
armor limit were agreed in chat with the user ("c'est bon pour moi, vas-y mais indique bien la limite pour le
blindage"); everything marked **[call]** was decided by the builder after three independent reviews (data, front-end,
game logic) or a real-data check and is listed again in section 10. Written in English like the rest of the repo; the
UI ships in the 11 locales.

## 1. Intent

A player picks a vehicle type, a play style, a game mode and a BR. The app answers two questions from the game's own
stats and flight models:

1. **Which vehicle is strongest for my style at this BR?** A ranked list of the vehicles at that BR.
2. **Against what will I fight, and who do I beat?** For a picked vehicle, every opponent it can meet (BR -1.0 to +1.0
   in that mode, all nations), each marked *advantage*, *even* or *disadvantage*, with the 2-3 stats that decide it.

The user's words: "trouver le meilleur véhicule qui a le plus d'avantage par rapport aux autres", "si je suis en BR 3.0
je peux voir du 2.0 et du 4.0", "trier par rang et par BR", "pense à tous les styles sur tous les types de véhicule",
"le plus important c'est la logique des stats, flight model", "indique bien la limite pour le blindage".

### Goals
- Every vehicle type (aircraft, helicopters, ground, naval) and the play styles players recognise for each (section 5).
- A duel logic that reads like a player's reasoning: who can force or refuse the fight, who shoots first, whose shot
  kills, who outlasts (speed and climb before turn time; penetration and reload; reach before firepower).
- Transparent: every verdict shows its reasons; the stats, weights and limits are visible in the page.
- Sorting by score, BR and rank; filters by rank, nation, owned vehicles; one BR or every BR.
- The armor limit stated plainly in the page wherever armor counts (section 7).

### Non-goals
- Pilot skill, team play, maps, spotting, effective (line of sight) armor, weak spots, damage models, how often a
  vehicle is played. None of these is in the data.
- Live data from the game or the internet. Everything comes from data/ built from the game files.
- A battle simulator. Duels are stat comparisons with thresholds, not physics simulations.

### Anti-goals (a failure even if it works)
- A verdict like "cannot penetrate" or "immune" drawn from card armor. Card armor is nominal and inconsistent (section 7).
- Hidden weights. A score nobody can explain is worse than no score.
- Breaking the Vehicles page, the compare dialog (or the user's saved compare tray), What changed, or user data.
- Comparing values that are not comparable: propeller hp/t against jet thrust-to-weight, the card manoeuvre placeholders
  of helicopters, a helicopter's air speed against a tank's road speed, an autocannon's per-shot time against a tank
  gun's reload.

## 2. Constraints (measured on data built from game 2.61.0.20)

- vehicles.json (2.0 MB) loads at boot; details.json (13.8 MB) loads one vehicle at a time through `/api/vehicle/<id>`.
  **Everything the ranking needs must be in vehicles.json `s` / `su` or a record field.**
- BR arrays are `[AB, RB, SB]` on the .0/.3/.7 grid; `hgSteps(a, b) = round((a - b) * 3)`; a window is |steps| <= 3.
  Naval has no Simulator battles (its SB value repeats RB). Air SB and ground SB use rotating brackets: the +-1.0
  window is an approximation there.
- **Opponent pool** (and candidate pool): leave out hidden (`h`), rarity `ra` 6, mod package vehicles (`mod`), AI
  support units (ids containing `killstreak`, starting with `nt_`, `uav_`, `ucav_`), game-mode copies nobody owns
  (ids containing `tutorial`, `_race`, `_event`, `missile_test`, ending in `_arena` (the Arena-M tanks stay),
  `football`, `yt_cup`, `snowball`; the builder may find a data flag that does this better) and the launchers of a SAM
  system (ids ending in `_launcher`: the 10 TELs fight through their own vehicle, so each system counted twice).
  Removed vehicles (`ra` 5) otherwise stay as opponents (players still own them).
- Helicopter card values for turn, roll, wing loading, speed altitude and T/W are placeholders (turn 2.0 on 89/119):
  only `spd`, `climb`, `ceil` are usable for helicopters.
- Propeller aircraft carry `pw` (hp/t), jets and rocket aircraft `tw` (after the fix in section 3). A duel never
  compares a `pw` with a `tw`. "Jet" in this document means "has `tw`".
- Card armor (`armT`, `armH`) is nominal plate thickness: see section 7. Missing on about 1 ground vehicle in 5.
- Armament `rng` is a missile's flight range, not its launch range; IR SAMs without inertial guidance show 8 000 or
  10 000 m.
- Scripts: no inline handlers or inline `<script>` (tests/test_safety.py), one global scope (prefix `bv`/`BV`), every
  name through `esc()`, static strings through `data-i18n`, dynamic ones through `t()`.

## 3. Data: what the builder adds (wtftd/builder.py)

### Rules for all new keys
- **Written only when the vehicle has the thing** (no zeros in vehicles.json, so the panel and compare dialog show no
  empty rows). The engine reads an absent *capability* key as 0 (section 4). A *measured* stat keeps a measured 0
  (`dep` 0: rails that cannot point down, BM-13N): left out, the duel would skip it, as it does a fixed launcher's
  (call 36).
- `su` holds the stock value where a modification changes it: an absent key means "same as upgraded", 0 means "the
  stock vehicle lacks this capability", `null` means "unknown in stock" (a *measured* stat the stock vehicle lacks,
  for example `vel` when the stock main gun has no unguided round, or a missile carrier no missile); the engine and
  `statAt` read that `null` as unknown, never as a fallback to `s`. **Stock presets**: a preset is stock when neither
  it nor any slot preset it uses needs a modification (`req` on the preset, `reqModification` on slot presets) but a
  free one, judged as shells are (the hidden `ship_torpedoes` every naval torpedo preset needs: tier 0, no cost);
  official presets only, not a custom loadout of the free slot presets. **[call]** **Stock shells**: the default set
  plus ammo modifications that are free and need nothing (tier 0, no cost, no `reqModification`); researched shells
  (`<shell>_ammo_pack` requirements) are not stock. A set the shared modification table gives under another name is
  official (`effects.additiveBulletMod`: the T-34's `76mm_AP_1942` gives its `76mm_ussr_AP_1942`), and stock when that
  modification is free. **Stock speed of boats and ships**: `spd` x the `mulMaxSpeed` of the modifications that apply
  while not researched (`invertEnableLogic`: hull 0.97, screw 0.95, engine 0.93, so 0.857 on 589 of the 590 playable
  vessels: Fletcher 65 -> 56 km/h, as on the official wiki's card). Sensors: `sy.su`.
- Each key gets a `STATS` entry in web/stats.js (sortable and filterable in the Vehicles list) and a `stat.<key>` label
  in every locale. Keys already shown elsewhere in the panel or the compare dialog (`vne`, `stab`, `dep`, `th`, `rf`,
  `rad`, `cm`, `rwr`) get a STATS flag so they are not shown a second time as a panel tile or a compare row. `pen` gets
  its own hint (not the armor "front / side / rear" hint that `triple` stats get today). `statAt` learns to return a
  stock array from `su`.
- Bump `SCHEMA` so installed data rebuilds.

### New keys

| key | types | unit | definition |
|---|---|---|---|
| `fg` | air, heli | kg/s | Forward guns' burst mass, best preset: the fitted forward guns plus that preset's forward guns, pods included **[call]** (gondolas and gun pods: call 15) (trigger `machine gun`, `cannon` or `additional gun`; helicopters: also `gunner0` to `gunner2`, the chin gun and the UH-1 family's flexible forward guns (XM21, XM-30): no helicopter has door guns; not the upward-firing Schräge Musik guns, `schraegeMusikAngle`). Fitted: the unit's own weapons or, upgraded, those of a modification that replaces them (`effects.commonWeapons`: the Yak-9UT's N-37, the Bf 109 G-6's MK 108). Per gun: shots/s (Weapon override, else the gun file's `shotFreq`) x mean projectile mass of the default belt. Read from the unit's weapons, not from `am`. Checks: Bf 109 F-4 3.1 (stock 1.7: its gondolas' preset needs a modification), P-51D about 3.2, Fw 190 A-8 about 6.2, MiG-15bis about 10.9, Javelin FAW.9 about 20.8, Mirage IIIC about 10.1. Stock: the unit's own fitted guns with the best stock preset. |
| `vne` | air | km/h | Dive limit, indicated (`st.lim.v`; swept wings: the swept-back value). |
| `pay` | air, heli | kg | Heaviest preset of ground ordnance: bombs, guided bombs, rockets (rocket pods: container mass + rounds x round mass; the catalog's missing container mass is fixed), torpedoes, mines, nuclear, AGM, ATGM. Not AAMs, fuel, targeting pods, gun pods. Each weapon's catalog mass is rounded to 0.1 kg before the count multiplies it (Me 262 A-1a 187.2 for the file's 184.8: about 1%). |
| `rkt` | heli | kg | Internal (no STATS entry): `pay` without the guided weapons (`atg` and the others count them), the heaviest preset of unguided rockets and bombs (weapons.json categories `bombs`, `rockets`). Rockets and guns reads it. 109 of 119 helicopters; BO 105 PAH-1 54, its 6-rocket pod (stock 0: the pod's slot presets need a tier 3 modification). |
| `ir` | air, heli | count | Most IR air-to-air missiles in one preset. |
| `irq` | air, heli | 1-3 | Best IR AAM: 1 rear-aspect, 2 all-aspect, 3 all-aspect with IRCCM. |
| `rm` | air | count | Most radar-guided air-to-air missiles in one preset; not anti-radiation ones (Sidearm) nor those steered by hand (MCLOS: AA.20, X-4). |
| `rmq` | air | 1-2 | Best radar AAM: 1 semi-active, 2 active. |
| `rmr` | air | km | Longest radar AAM `rng` (flight range; the same scale for every radar AAM). |
| `rad` | air, heli, ground, naval | km | Longest search radar range (radar / radar_irst entries with a search role). Aircraft and helicopters: the range against aircraft **[call]** (call 16), from the radar's file: transceivers its fsm uses only with signals that cannot see aircraft (`aircraftAsTarget` false: sea or ground search) are left out, and a radar none of whose signals can see aircraft counts 0 (Buccaneer). |
| `cm` | air, heli | count | Countermeasure charges: fitted launchers (the unit's weapons, a modification's replacing set included as for `fg`) plus the most carried in countermeasure pods in one preset. |
| `rwr` | air, heli | 1 | Has a radar warning receiver. |
| `def` | air | count | Defensive turrets: distinct `gunnerN` triggers among the fitted weapons (B-17G 9, Il-2M 1). Not on helicopters. |
| `atg` | air, heli, ground | count | Most anti-ground guided weapons in one preset (aircraft, helicopters; a pod counts its rounds) or carried (ground): ATGM (MCLOS ones included), AGM, guided bombs. **Not** anti-radiation missiles (guidance `arm`) nor anti-ship ones: a seeker whose `targetRadiusMin` is 10 m or more (Harpoon 15, Penguin and ASM-2 10, GCS-1 30; seekers that lock on tanks: 1.5). Ground: each gun or launcher counts its rounds once (rounds x barrels), but a gun's missiles no more than a spawn may carry when every missile set has a wpcost `maxToRespawn` (their sum: T-90A 28 of 43); a launcher whose file has no ammo set (an M113's TOW, a BMP-1's Malyutka) counts its fitted rounds, and upgraded also those of a modification that replaces the fitted weapons (`effects.commonWeapons`: the BMP-1P's Konkurs); a SAM fired from an ATGM ammo set (ADATS) is an ATGM too, with that set's penetration. |
| `atr` | air, heli, ground | m | Longest range of those weapons: `rng` capped at 10 000 m; a guided bomb without `rng` counts 8 000 m. |
| `atp` | heli, ground | mm | Best penetration of those weapons. |
| `atq` | air, heli, ground | 1-2 | 2 when one of them is fire-and-forget (IR, TV, active radar or GPS guidance: armament's `ff`, JDAM-type bombs included), 1 when all need guiding to the hit. |
| `pen` | ground | mm, triple | Main gun only (fix 4 below): best penetration at 500 / 1000 / 2000 m over the shells the vehicle normally has (not the `x` shells), kinetic curves interpolated, HEAT constant, gun-launched ATGMs included. `statVal` gives the 500 m value. Missiles on a separate launcher are in `atg`/`atr`/`atp`, not here. |
| `vel` | ground | m/s | The speed the game's bullet card gives the fastest round the main gun normally has, every round of a belt, but guided missiles and rounds that pierce nothing (smoke, flares, practice...): APFSDS, APDS, AP..., HEAT or HE when the gun has nothing faster (a HEAT-only recoilless rifle: its HEAT's), an unguided rocket's top speed (`maxSpeed`, else `endSpeed`). Gun-launched ATGMs never set it (their reach is `atr`). A missile carrier (`gl`) has none of those: its fastest missile's speed (armament `v`: RakJPz 2 220, M901 296, Khrizantema-S 550, Tor-M1 850; stock: its stock missiles', `null` when none). **[call]** (call 22) |
| `dep` | ground | deg | The main gun's depression, one decimal (`-sy.el[0]`, its pitch limit: T-90A 4.5), never below 0 (BM-13N's rails rise 7 degrees at least: 0). A missile carrier's is its launcher's pitch; a fixed launcher (`sy.el` [0, 0]: Swingfire, Striker, Type 60 ATM, LOSAT, SAM launchers) has none, its missile steering after launch **[call]** (call 36). |
| `stab` | ground | 1-2 | Stabilizer: 1 vertical, 2 two-plane. |
| `rf` | ground | 1-2 | Rangefinder: 1 optical, 2 laser. |
| `th` | ground, heli | 1 | A thermal sight for the gunner (ground) or the gunner or targeting sight (helicopters: `sy.nv` `g` or `s`). |
| `auto` | ground | 1 | The main gun is automatic: one barrel fires a shot a second or more (the gun file's `shotFreq` over the tubes the Weapon fires in turn, `emitterGenRange`), so its `rel` is a per-shot or magazine time, not a reload: Gepard, ZSU-23-4, BMPT, 2S38, OTOMATIC; not the M50 Ontos's six rifles, a rocket launcher or a missile carrier. Internal: no STATS entry. **[call]** (call 29) |
| `gl` | ground | 1 | A missile carrier: every round its main gun normally has is a guided missile (bullet type `atgm...` or `sam...`), or its main weapon is a launcher without an ammo set that fires one (the M113A1 (TOW)s). Internal (no STATS entry, never in `su`). 91 vehicles, 68 of them in the pool: ATGM carriers (RakJPz 2, M901, Jaguar 2, Khrizantema-S...) and SAM vehicles (Tor-M1, Osa, NASAMS...), 24 of the 68 with `atg`. **[call]** (call 22) |
| `sam` | ground | m | SPAA missile reach: an IR SAM that locks on before launch reaches as far as its seeker locks on from any side (`aa`; without it, from behind: `lk`), no farther than its `rng`, a flight range (Strela-10M2 3200, Gepard 1A2 6000); an IR SAM with inertial guidance locks on in flight (IRIS-T SLM, Python 5) and gives its `rng`, as radar and command-guided SAMs do (2S6 8000, upgraded 10000). |
| `aab` | ground | kg/s | SPAA guns' burst mass (same method as `fg`). |
| `fm` | boat, ship | kg/min | Main battery: weapons of trigger group `primary`, 60 x shots/s (Weapon override, else the gun file) x shell mass; upgraded, a modification's replacing set counts when it fires more (Flagstaff's 40 mm). Fletcher about 2700, Admiral Hipper about 4900. |
| `fa` | boat, ship | kg/min | All guns firepower: as `fm`, over every gun of the fitted set, not only group `primary` (a boat's 40 and 20 mm secondary and machine-gun groups). Guns only: no rockets, depth charges, bomb mortars or torpedoes. Stock: its own set (`null` when it fires nothing). PGM-9 764 (`fm` 103), Krischan der Grosse 756 (151), S-100 371 (195), Le Brestois 2341 (810: its 4 x 57 mm are secondary), Fletcher 3312 (2700). |
| `tor` | boat, ship | count | Most torpedoes (presets or ammunition). A preset counts a torpedo tube's torpedoes on any trigger: on the gun triggers (`gunner0`, `gunner1`, `cannon`, `machine gun`, `additional gun`) only guns count barrels (`preset_composition`: L'Intrepide 7, S-61 4, SUB Tang 26) **[call]** (call 35). |
| `torr` | boat, ship | m | Longest torpedo range. |

Record field (not in `s`): **`bt`** on aircraft, the BR in ground battles `[AB, RB, SB]`: RB from
`economicRankTankHistorical`, SB from `economicRankTankSimulation`, each falling back to the aircraft's own BR when
absent; AB = the aircraft's AB BR. Written only when it differs from `br`.

### Data fixes made on the way (they change rankings and existing columns)
1. `kin` / `heat` leave out shells the vehicle does not normally have (`x`); `heat` counts gun-launched ATGMs. A set
   the shared modification table gives (`additiveBulletMod`, the rules above) is no longer `x`: 75 shells on 36
   vehicles (T-34 (1941) `kin` 87 -> 99; T-34 (1942), SU-76M: `kin` 125, `heat` 80, `vel` 950; T-28 `kin` 67), on the
   Vehicles page's shell list too. A kinetic missile (the LOSAT's MGM-166, `atgm_ke`) gives `kin` its best figure and
   no `heat`; armament's `pen` takes a table's first value when it has none at 0 m (its table starts at 1000 m: `atp`
   775).
2. **Power or thrust by engine kind.** The card puts the value in the wrong field on about 75 aircraft (Mystère IVA
   `pw` 410 is a thrust-to-weight 0.41; Fokker D.21 `tw` 0.35 is a power-to-weight 350 hp/t). The kind of engine
   decides: jet or rocket engines give `tw`, propeller engines (inline, radial, turboprop) give `pw` (x1000 from the
   card's hp/kg). Mixed (Fireball: radial and jet) keeps `tw`. Then the "card counts one engine" test runs for both:
   `pw` with power (`card_engine_factor`, done), `tw` with the flight model's static dry thrust
   `EngineType0.Main.ThrustMax.ThrustMax0` (kgf; older models without it: `Main.Thrust / 9.81`). Must double the
   Me 262, Meteor F.8, Canberra B.2 and B(I)6, B-57B, F3D-1 and the Chinese Il-28; must keep the F-5A/E, Saab 105 and
   the Soviet Il-28. Tests cover both lists. Then every propeller card, multiplied or not, is brought within 15% of the
   flight model's figure for all engines at the lightest mass, both ways (`fm_power_ratio`: Power x AfterburnerBoost
   over EmptyMass + MaxFuelMass0 + OilMass), where the reference twins land at 0.94-1.11. **[call]** (calls 28, 34)
3. Weapon key to armament item: needed for missiles, SAMs and torpedoes. **[call]** How it is stored is the builder's
   choice. As built: a key goes through the pods (a container's inner weapon and rounds) first, then the file's own
   items, else the key without `(_default|_\d+)$`: 5714 of 5714 guided preset keys map (34 through pods); ground ammo
   sets are looked up by bullet name.
4. **The main gun** (`builder.main_gun`; `cal`, `kin`, `heat` and the ground keys above read it): the gunner's
   (`gunner0`) or the first Weapon block's ammo group, else (a dummy turret, a launcher listed after a machine gun) the
   largest caliber, never a machine gun under 15 mm: the LOSAT's MGM-166 launcher and the Type 60 ATM's Type 64 MAT,
   not their M2 (which gave them `cal` 12.7, `vel` 944, `auto`). A launcher without an ammo set is no ammo group: one
   of unguided rockets stands in as the main gun (`unguided_launcher`: Type 75 MLRS, BM-13N, judged on their rockets:
   **[call]**, call 30); a guided one makes the vehicle a missile carrier with no main gun (`gl`: the M113A1 (TOW)s).
5. **`cal`**: the round's caliber as the game's bullet card reads it, a rocket inside a placeholder bullet giving its
   own (BM-8-24 82 mm, not 150; Type 81 TanSAM 160, not 80). Boats and ships: the largest in trigger group `primary`,
   the guns `fm` counts (MPK-201K 45, not its first ammo group's 25 mm), else the first ammo group's. It follows the
   game's trigger groups: five boats file their 76.2 mm as secondary (LCS(L)(3), SGB 304, SGB 309, PCE-842, Yuri
   Asagao: 40) and the 70 ft MGB its 40 mm (12.7), which the Vehicles page shows as their "Main gun caliber".
6. **`wl`**: a card below 25 kg/m² is a broken card: no `wl`, no `su.wl` (P-39Q-5 18.26 where the P-39N's says 166;
   the lightest real card is the Po-2's 32).

Not in this work (found while mapping, for later): the autoloader flag `sy.al` is never written, so the compare
dialog's autoloader row is always empty; naval citadel armor exists in the cards but is as nominal as tank armor.

## 4. The duel

A duel compares the candidate **A** with one opponent **B** on the stats of the style.

**Kinds of stats.** *Measured* stats (speed, climb, turn, penetration, reload, armor...): absent means unknown, the term
is skipped. *Capability* stats (`fg`, `pay`, `rkt`, `ir`, `irq`, `rm`, `rmq`, `rmr`, `rad`, `cm`, `rwr`, `def`, `atg`,
`atr`, `atp`, `atq`, `stab`, `rf`, `th`, `sam`, `aab`, `tor`, `torr`): absent means 0. When both sides are 0 the term is
skipped (it tells nothing); 0 against a positive value is decisive.

**A term that needs a stat** (a style's `need`): compared only when either side has that stat (> 0), else out of the
coverage too; a side's value reads 0 when the other side lacks it (its flares have no IR missile to decoy) **[call]**
(call 32). Flares act on IR missiles only: Turn fighting's `cm` needs `irq`, Missiles and radar's and
Anti-helicopter's `cm` need `ir`. **[call]** (call 20)

**Per stat** `k` with weight `w`, even band `e` and decisive threshold `d`:
- absolute stats: `delta = dir(k) x (A - B)`;
- relative stats (marked %): `delta = dir(k) x ln(A / B)`, thresholds `ln(1 + e)` and `ln(1 + d)`, so the term is the
  same seen from either side. **[call]**
- `dir(k)` is the duel's own direction table (+1 higher is better, -1 lower is better; e.g. `crew` +1, `turn` -1;
  `disp` +1 except in Torpedo attack where -1), independent of STATS' `better`.
- term `t = sign(delta) x clamp((|delta| - e) / (d - e), 0, 1)`: 0 inside the even band, 1 from the decisive
  threshold on, linear between.

**Duel score** `D = sum(w x t) / sum(w)` over the terms not skipped. **Coverage**: the weight of the style's measured
stats known on both sides plus the weight of all its capability stats, over the style's total weight (terms a rule
never compares for that pair are out of both: a mixed jet / propeller `pwr`, armor from BR 8.7, an autocannon's
`rel`, a missile carrier's `cal` (a missile's diameter), a term whose `need` neither side has). Below 60%: verdict
*not enough data* (shown grey, left out of the counts).

**Verdict**: *advantage* when `D >= 0.2`, *disadvantage* when `D <= -0.2`, else *even*. Then the style's **gates**
apply (section 5).

**Reasons**: the 3 terms with the largest `|w x t|`, shown as "Turn time 18.0 s vs 20.5 s" in the house colours
(`chip info` = better, `chip warn` = worse), plus the gate's sentence when a gate changed the verdict.

**Pair terms** (computed from both vehicles):
- `reach` (metres): A's reach against B's standoff (helicopters, SPAA, close air support; section 5 gives each side's
  value). Absolute, even 500 m, decisive 2000 m in every style that has it (`BV_WIDE`; no style keeps the table's 300 /
  1500 m: call 27).
- `front` (ground, nominal armor): `ln((A.pen / B.frontMin) / (B.pen / A.frontMin))` where `frontMin` is the smaller
  of the hull and turret front values and `pen` is at the style's range. Even 0.1, decisive 0.5.
- `side` (ground, nominal armor): `ln(A.pen500 / B.sideMax)` (larger of hull and turret side): even 0.1, decisive 0.3.
- Both armor terms count **only when both vehicles' BR in the mode is below 8.7**, and their reasons carry the armor
  asterisk (section 7).
- `kill@r` (ground): the larger of A's `pen` at r and A's `atp` when A's `atr >= r`; used by Sniper and Ambush so a
  missile carrier is judged on its missile.

**Gates** (applied after the verdict, each with its sentence):
- *Can refuse your turn fight* (Turn fighting): B is faster by more than 4.5% and climbs more than 15% better: at best
  *even*.
- *You can't get above it* (Boom and zoom): B is faster beyond the even band and climbs better beyond 8%:
  *disadvantage*.
- *Outgunned* (Brawler, Sniper, Ambush): A's penetration at the style's range is below half of B's: *disadvantage*.
  Sniper and Ambush compare `kill@r` (a missile counts), Brawler `pen@500`; the `front` term reads the same values.
  Only where armor counts, both vehicles below BR 8.7: from there a shaped charge's millimetres and a dart's don't
  compare. **[call]** (call 21)

Thresholds are compared with a 1e-9 tolerance, so an exact 0.2 (or an exact 15%) falls where the rule says.

**Vehicle score**: over the opponents with a verdict, `net = (wins - losses) / count`; a style with two opponent
groups (Close air support: SPAA and fighters) takes the mean of each group's `net`, so each weighs half whatever its
size (the wins / even / losses shown stay the sums). **[call]** (call 19) Styles with a mission part add
`mission`: for each mission stat, the candidate's percentile among the **population** (the style's candidates, by the
style's rule, within the candidate's window; ties count half: `(below + 0.5 x equal) / n`; capability stats absent = 0;
a measured stat unknown for the candidate is dropped and the weights renormalised), the weighted mean of those
percentiles mapped to -1..1. `score = (1 - m) x net + m x mission`. Shown as 0-100 (`(score + 1) x 50`) with wins /
even / losses. Ties: higher mean `D` first. Filters (rank, nation, owned, removed, *Only vehicles made for this style*)
hide rows; they never change a score.

**Mode**: weights get a per-mode factor where the mode changes the game (air AB: turn x1.3, `fg` x1.2, climb x0.8,
speed x0.9; ground AB: `th`, `rf` x0.5, `dep` x0.7, `pw` x1.2; helicopter AB, in ground battles too: `th` x0.5). SB uses the RB weights and shows the approximation
note. Naval has no SB.

**Stock / upgraded**: the page has the Stock / Fully upgraded switch. Stock applies to the **candidates only**;
opponents are always fully upgraded (what a new owner meets). **[call]** Close air support and Missiles and radar also
pick their candidates on what the stock aircraft carries (`pay`, `atg`; `ir`, `rm`: call 33; the BR list follows); the
other styles pick them on upgraded values and judge them on stock ones (a helicopter with no stock missile stays an
Anti-tank missiles candidate, with no reach).

## 5. Styles

Default thresholds (a style can override):

| stat | kind | even | decisive |
|---|---|---|---|
| spd, propeller pair | abs | 10 km/h | 30 km/h |
| spd, both jets | abs | 50 km/h | 100 km/h |
| spd, mixed pair | % | 2% | 6% |
| climb | % | 8% | 20% |
| turn (lower better) | % | 5% | 10% |
| roll | % | 10% | 30% |
| wl (lower better) | % | 7% | 20% |
| pw | % | 5% | 15% |
| tw | abs | 0.05 | 0.10 |
| fg, aab, pay, rkt | % | 15% | 50% |
| vne | abs | 30 km/h | 80 km/h |
| ceil | % | 5% | 15% |
| ir, rm, tor, def, atg | abs | 0.5 | 2 |
| irq, rmq, atq, stab, rf, th, rwr | abs | 0.5 | 1 |
| rmr, torr, atr, atp, sam | % | 10% | 30% |
| rad | % | 15% | 50% |
| cm | % | 20% | 60% |
| crew, aircraft | % | 20% | 50% |
| ground spd, rev | abs | 5 km/h | 15 km/h |
| ground pw | abs | 2 hp/t | 5 hp/t |
| pen, kill@r | % | 10% | 30% |
| vel | % | 8% | 20% |
| rel (lower better; skipped when either main gun is `auto`) | abs | 0.5 s | 1.5 s |
| trav, vert | % | 20% | 50% |
| dep | abs | 1 deg | 3 deg |
| cal (skipped when either side is a missile carrier, `gl`) | % | 10% | 40% |
| crew, ground | abs | 0.5 | 2 |
| naval spd | abs | 5 km/h | 10 km/h |
| fm, fa, crew naval, disp | % | 20% | 50% |

`pwr` below means `pw` for propeller aircraft and `tw` for jets (a mixed pair skips it).

### Aircraft (type "Aircraft")
Window on the aircraft BR, except Close air support (ground-battle BR `bt`, its opponents' `bt` for aircraft and `br`
for SPAA).

| style | candidates | opponents and duel | mission (m) |
|---|---|---|---|
| Turn fighting | every aircraft **[call]** (call 37) | every aircraft: turn 1.5, wl 1.0 **[call]** (call 17), ind 1.0 (call 38), pwr 0.6, fg 0.5, climb 0.4, roll 0.3, irq 0.3, spd 0.2, cm 0.2 (needs irq). Gate *can refuse your turn fight*. | - |
| Boom and zoom | every aircraft (call 37) | every aircraft: spd 0.9, climb 0.8, fg 0.8, roll 0.6, vne 0.6, pwr 0.4, ceil 0.3, turn 0.1, wl 0.1. Gate *you can't get above it*. | - |
| Energy fighting | every aircraft (call 37) | every aircraft: pwr 1.0, climb 0.9, spd 0.6, turn 0.5, ind 0.5 (call 38), roll 0.4, fg 0.4, wl 0.3 | - |
| Bomber hunting | every aircraft (call 37) | k bomber, and k assault without radar AAMs (`rm`) **[call]** (call 18): spd 1.0, climb 1.0, ceil 0.5 | fg 1.0, roll 0.2 (m 0.4) |
| Close air support (ground battles; RB and SB, AB shows the approximation note) | k assault, or k fighter / bomber with `pay` >= 500 kg or `atg` > 0 (in Stock: the stock aircraft's) | SPAA: `reach` 1.0 (A: `atr`, else 2000 m with bombs and rockets; B: `sam`, else 3000 m with guns), even 500 m, decisive 2000 m. Fighters: spd 0.8, climb 0.6, turn 0.4, cm 0.4, roll 0.3, def 0.3, fg 0.3. The two groups weigh half each **[call]** (call 19) | pay 1.0, atg 0.5, atr 0.5, atq 0.3, fg 0.3 (m 0.5) |
| Bombing | k bomber | k fighter: spd 1.0, ceil 0.7, def 0.6, climb 0.5, crew 0.4 | pay 1.0 (m 0.5) |
| Missiles and radar | jets with `ir` or `rm` (in Stock: the stock aircraft's **[call]** (call 33)) | every jet (call 37): tw 0.8, irq 0.6, rmr 0.6, rad 0.6, cm 0.6 (needs ir), spd 0.6, rmq 0.5, rwr 0.5, climb 0.5, turn 0.5, ir 0.3, rm 0.3, fg 0.2 | - |
| BVR (radar missiles) **[call]** (call 39) | jets with `rm` (in Stock: the stock aircraft's) | every jet: rmr 1.0, rmq 0.8, rad 0.7, spd 0.7, rm 0.5, rwr 0.5, cm 0.4 (needs rm: a side's countermeasures count against the other side's radar missiles only), climb 0.3, ceil 0.3 | - |

### Helicopters (type "Helicopters"; window on the helicopter BR, which ground vehicles share)
| style | candidates | opponents and duel | mission (m) |
|---|---|---|---|
| Anti-tank missiles | `atg` > 0 | ground vehicles: `reach` 1.0 (A: `atr`; B: SPAA `sam`, else 3000 m with guns; other ground vehicles their `atr` when they have one, else 2000 m), even 500 m, decisive 2000 m against every ground vehicle **[call]** (call 27) | atg 0.6, atq 0.6, atp 0.5, th 0.4, cm 0.3, rwr 0.3, spd 0.3, climb 0.2 (m 0.5) |
| Rockets and guns | `rkt` > 0 **[call]** (call 26) | SPAA only: `reach` 1.0 (A: 2500 m; B as above), even 500 m, decisive 2000 m: the same verdicts for every helicopter at a BR | rkt 0.8, fg 0.5, cm 0.6, spd 0.5 (m 0.5) |
| Anti-helicopter | `ir` > 0 or `fg` > 0 | helicopters: ir 1.0, irq 0.5, cm 0.7 (needs ir), fg 0.5, th 0.4, spd 0.3, climb 0.2 (no rwr: no helicopter has a radar missile) | - |

### Ground (type "Ground"; window on the ground BR)
Opponents: ground vehicles, SPAA included (except the SPAA style); Brawler leaves out the missile carriers (`gl`),
Sniper, Flanker and Ambush the SAM-only ones (`gl` without `atg`: they fight no ground vehicle) **[call]** (call 22).
With the filter off, a vehicle a style leaves out of its opponents duels nobody in it and gets no score (*Not made for
this style: no duels.*) **[call]** (call 31). `pen@r` is the `pen` value at r metres.
| style | candidates | duel | mission |
|---|---|---|---|
| Brawler | ro medium_tank, heavy_tank | rel 0.8, trav 0.7, cal 0.7, stab 0.6, pen@500 0.6, crew 0.4, pw 0.3, rev 0.3, `front` 0.15. Gate *outgunned* (at 500 m). | - |
| Sniper | ro medium_tank, heavy_tank, tank_destroyer | kill@2000 1.0, vel 0.7, dep 0.7, rev 0.6, rf 0.6, th 0.5, rel 0.5, trav 0.3, `front` 0.1 (each side's turret front). Gate *outgunned* (at 2000 m). | - |
| Flanker | ro light_tank, medium_tank | pw 1.0, spd 0.7, stab 0.7, trav 0.6, rev 0.5, rel 0.5, `side` 0.4 | - |
| Ambush | ro tank_destroyer (missile tanks included) | kill@1000 1.0, cal 0.8, rev 0.6, atr 0.6, rf 0.5, th 0.5, rel 0.5, trav 0.2, `front` 0.1. Gate *outgunned* (at 1000 m). | - |
| Anti-aircraft (RB and SB; AB shows the approximation note) | k SPAA | aircraft (their `bt`) and helicopters: `reach` 1.0 (A: `sam`, else 3000 m with AA guns (`aab`), else 0: with the filter off, a tank without AA weapons reaches nothing; B: `atr` when it has guided weapons, else 2000 m), even 500 m, decisive 2000 m | rad 0.8, aab 0.7, sam 0.6, vert 0.6, trav 0.4, pw 0.3 (m 0.5) |

### Naval (type "Naval": boats and ships together, they share battles; no SB)
Opponents: boats and ships in the window.
| style | candidates | duel |
|---|---|---|
| Gun brawler | boats | fa 1.0 **[call]** (call 24), crew 0.7, cal 0.6, disp 0.5, spd 0.4; the naval armor note (section 7) |
| Torpedo attack | boats and destroyers with `tor` > 0 **[call]** (call 23) | spd 0.9, tor 0.8, torr 0.8, disp 0.5 (smaller is better here), fm 0.3, crew 0.3 |
| Destroyer | ro destroyer | fm 0.9, spd 0.7, crew 0.6, tor 0.4 **[call]** (call 25) |
| Long range | ships that are not destroyers | cal 1.0, fm 0.8, crew 0.7, disp 0.5, spd 0.3 |

A toggle **Only vehicles made for this style** (default on) applies the candidates column; off, every vehicle of the
type is listed in that style (scores still come from the same opponents and the same mission population). **[call]**

## 6. The page

- **Where**: a new page *Best vehicles* in the Vehicles menu, right after *Vehicles* (`MENUS.vehicles`, subtab,
  `#view-best`, script `web/best.js`, prefix `bv`). **[call]**
- **Controls** (one bar, like the other pages): type (Aircraft, Helicopters, Ground, Naval), mode (AB / RB / SB; SB
  disabled for Naval), BR (each BR of the type, plus *Every BR*: each vehicle against its own window), style (with one
  line saying what it weighs, and one with the weights of its duels and second part in the mode picked), rank chips, nation chips, *Only my vehicles* (My hangar), *Include vehicles no longer
  available* (rarity 5, off by default for candidates), *Only vehicles made for this style*, Stock / Fully upgraded.
  The choices are kept in `store` (`bv`).
- **Result table**: position, vehicle (flag, picture, name, class, rank, BR), score bar 0-100, wins / even / losses,
  its strongest and weakest stats for the style against the window. Sortable by score (default), BR, rank, name.
  First 100 rows, then *Show more*. **[call]**
- **A row opens** its matchups: *Advantage*, *Even*, *Disadvantage* (and *Not enough data* when any), each opponent with
  flag, name, BR and its reasons. Actions: open the vehicle's panel (`showView('vehicles'); openVehicle(id)`), compare
  with an opponent (the app's compare dialog opened on just these two, **without changing the user's saved compare
  tray**), test drive.
- **Notes in the page**, always visible where they apply:
  - the armor limit (section 7) for every ground style, with an asterisk on every reason that uses armor, and the
    naval armor note on Gun brawler;
  - "Simulator uses rotating brackets: the +-1.0 window is an approximation" in SB, and the AB note for the close air
    support and anti-aircraft styles;
  - "Duels compare the game's stats only: skill, team, map and spotting are not counted" (always, small).
- **Refresh**: the page re-renders on its own controls, on the Stock / upgraded switch and on My hangar changes.

## 7. Armor limit (the user asked for it to be clear)

Text in the page (all ground styles, a visible note, not only a tooltip):

> Armor here is the stat card's plate thickness. It does not count slope, composite, ERA or spaced armor: sloped tanks
> (T-34, Panther) are better protected than shown, and from BR 8.7 (first ERA at 8.7, add-on armor at 9.0, composite
> at 9.7) these numbers mean nothing: the card gives a Leopard 2A6 turret 75 mm. So front armor counts very little
> (at most 0.15 of a duel), side armor a little more for flankers (side plates are mostly upright, so closer to the
> truth), and from BR 8.7 armor does not count at all, nor does the Outgunned rule (the penetration of a shaped charge
> and of an APFSDS dart don't compare). The Brawler ranking, where armor decides most in game, is the least reliable.

Every reason built from armor ends with an asterisk that carries the same text as a tooltip. Nothing in the page says
"cannot penetrate" or "immune". Measured: Brawler puts the armored heavies last, all four Tiger H1s and both IS-1s at
RB 5.7 (28), the IS-3 and IS-4M last but one and last over every BR (call 1).

Boats and ships have no armor in the data. Gun brawler, where armored boats are the toughest brawlers in game, shows:

> Armor is not counted for boats and ships: armored boats (Pr.1124, Pr.1204, MBK-161) are tougher brawlers than shown.

## 8. Tests

- Python, made-up inputs: each new stat (built-in vs pod vs defensive guns, chin gun, Weapon shotFreq override, payload
  with rocket pods and stock presets through slot `reqModification`, AAM counts and kinds, radar, countermeasure pods,
  turrets, guided weapons without anti-radiation / anti-ship and with the 10 km cap and the 8 km guided-bomb default,
  `pen` interpolation and `x` shells, `vel` fastest unguided shell, `dep`, `stab`, `rf`, `th` for ground and helicopters,
  `auto`, IR vs radar SAM reach, naval primary battery, torpedoes, `bt`, free stock ammo), the `kin` / `heat` fixes,
  the engine-kind `pw`/`tw` fix and the twin-jet lists above.
- JS with node (the tests/test_hangar.py pattern, loading stats.js, hangar.js, best.js): absolute and log-ratio terms
  in and out of the even band, both directions, capability 0-0 skipped and 0-vs-positive decisive, unknown measured
  stats, coverage and *not enough data*, verdict thresholds, the three gates, pair terms and the 8.7 armor cut, the
  window (+-3 steps), opponent filters (hidden, rarity 6, AI units, game-mode copies, mods), mission percentile with
  ties and the final score, ranking order and ties, mode factors, stock candidates against upgraded opponents,
  `statAt` with a stock array.
- After the real-data checks, each fix with its test: free requirements, naval stock speed, `fa`, naval `cal`, sets the
  shared modification table gives, the main gun's pick, `gl` and a missile carrier's `vel`, the LOSAT's `atp`, `auto`,
  `dep`, `cal` of a rocket in a bullet, `wl`, `rkt`, helicopters' gunner1 and gunner2, the power cap (both ways), a
  torpedo tube on a gun trigger, a fixed launcher's `dep`, the build's guards (a vehicle whose duel or guided stats fail
  keeps its record); in the engine, the groups' mean, stock Close air support and Missiles and radar candidates, `need`
  (a side's flares against the other's IR missiles), the styles' own opponents (`self`), the gate's 8.7 cut, missile
  carriers' opponents, the Anti-aircraft reach, Torpedo attack's candidates, the pool's launchers, Rockets and guns on
  `rkt`.
- Locales: every new key in the 11 locales, non-empty, same placeholders as English (tests/test_challenges.py pattern).
- Real data (a check run before release): turn fighting at RB 3.7 puts Spitfires, Zeros, Yaks near the top; boom and
  zoom at 5.0 puts Fw 190 Ds near the top; bomber hunting favours heavy cannon fighters; sniping at 6.7 favours
  high-velocity guns; Brawler at 5.7 no longer puts armoured cars on top; the armor note shows on ground styles.

## 9. Left to the builder
- How the weapon-to-armament mapping is stored; where in builder.py the new stats are computed; the data flag for
  game-mode copies if one exists.
- Exact markup and CSS, reusing the house blocks (`.fl-bar`, `.seg`, `.chip`, `ar-table`, `.ar-score`, `.hint`).
- The wording of labels and style descriptions, within the meaning above; translations in the 11 locales.
- Whether the panel of a vehicle gets a link to its Best vehicles ranking (nice to have, not required).

## 10. Calls made without the user (to check while reading)
1. Armor: front at most 0.15, flanker side 0.4, none at all when either vehicle is at BR 8.7 or above; the note says so.
   Brawler then puts the armored heavies last (section 7).
2. Naval boats and ships as one type, since they share battles; no SB for naval.
3. Only vehicles made for the style by default; removed vehicles kept as opponents (except game-mode copies and a SAM
   system's launchers), off as candidates by default.
4. Every opponent counts the same (the data has no play counts); Close air support's two groups weigh half each
   (call 19).
5. Helicopter manoeuvre values not used (placeholders in the game files).
6. The page sits in the Vehicles menu after Vehicles.
7. Relative stats compare as a log ratio, so a duel reads the same from both sides.
8. Stock applies to the candidate only; opponents stay fully upgraded.
9. Close air support is judged in ground battles (SPAA and fighters at the aircraft's ground-battle BR).
10. Light tanks, armoured cars and IFVs are not Brawler or Sniper candidates; a gun with less than half the
    opponent's penetration loses that duel (below BR 8.7: call 21).
11. `vel` is the fastest round of the main gun except guided missiles and rounds that pierce nothing (it was kinetic
    only): a HEAT-only recoilless rifle (M50 Ontos, Type 60 SPRG) topped Sniper 6.7 because its missing `vel` was
    skipped instead of lost. A missile carrier's is its missile's speed (call 22).
12. Sniper's `front` reads each side's turret front (the duel stays the same from both sides); the outgunned gate and
    `front` use `kill@r` in Sniper and Ambush, so a missile carrier can outgun a gun tank (below BR 8.7: call 21).
13. Helicopters get the ground AB factor on `th`; Close air support has no helicopter opponents.
14. A stock aircraft carries its official presets that need no modification, never a custom loadout of the free slot
    presets (upgraded values count official presets only too). An aircraft whose every preset needs one (12 playable:
    F-4S, F-2A ADTW, Su-30MKK...) gets its stock `fg`, `pay` and `cm` from its fitted weapons alone and no stock
    missiles, and 29 playable aircraft and helicopters in all show less in stock than their free slot presets carry
    (measured on the game's files of 2026-11-17): F-4S `fg` 0 though its Mk 4 gun pod is free, Su-30MKK `pay` and
    `ir` 0 with 4650 kg and two R-73E free, Su-25TM `atg` 0 with four free S-25LD. Counting each preset's free slot
    presets would fix them, in duelstats and in guided_stats (which reads `_sp`, a list of preset ids).

Calls 15 on came with the real-data checks (game 2.61.0.24, 2026-11-17 and 18), each with its reason and what it
changed, measured on the built data.

15. `fg` counts gondolas and gun pods: the best preset's forward guns join the fitted ones, as the definition says;
    counting only the guns every preset repeats gave the Mirage IIIC, F-104S and MiG-21 PFM none. 76 fighters gain more
    than 15% (F-4E 39.9 against 10.0 fitted, F-5E 21.8 against 5.6), Turn fighting's and Boom and zoom's `fg` too;
    stock keeps the fitted guns when the pods need a modification (Bf 109 F-4 3.1, stock 1.7: its R1 gondolas).
16. Aircraft `rad` is the range against aircraft: a radar that cannot search the air gave decisive terms in Missiles
    and radar. Buccaneer 278 km -> none (the S.2 and S.2B are candidates there), JA37 and AJ37 100 -> 70 (their sea
    transceiver), Mosquito FB Mk VI ASH, TR Mk 33 and PBM-5A 27 -> none, F-16C Block 50 90 -> 85. Ground and naval
    keep their longest search radar.
17. Turn fighting weighs turn 1.5 and wing loading 1.0 (were 1.0 and 0.6): with 1.6 of 3.6 against 2.0 for power,
    guns, climb, roll and speed, energy fighters won turn fights (P-39Q-25 over the A6M2, D 0.22). That duel is now even
    (D 0.07), La-5FN against A6M2 a disadvantage (-0.22); RB 3.7 keeps the Spitfires 1st to 3rd.
18. Bomber hunting meets bombers and the attack aircraft without radar air-to-air missiles: at jet BRs the attack
    aircraft are strike fighters (RB 15.0 held only F-15Es and the Su-34: every fighter 1/0/4). 12 aircraft leave the
    opponents (F-15E, EX, I and IA, Su-34, AV-8B+ x2, M-346FA, Hawk 200 RDA, Su-39, JH-7A2, JF-17); from 14.0 up the
    lists are the second part alone.
19. Close air support: its SPAA and its fighters each weigh half of the duel score, and in Stock it takes what the
    stock aircraft carries. Fighters outnumber SPAA 3 to 7 times in a window and outvoted them: GRB 11.7 put the F-15J,
    Su-27 and J-11 with unguided bombs above the Su-25T and Su-39 (8th, 9th), and Stock filled the list with aircraft
    carrying nothing (424 of 871 candidates; Lightning F.53 1st at GRB 8.7). Now GRB 11.7: Tornado IDS ASSTA1, Su-24M,
    Su-25T, Su-39, F-111C, MiG-27K, then Su-27, J-11; GRB 8.7: A-4B, Super Mystere B2, Buccaneer S.1, Sea Vixen FAW.2;
    542 candidates in Stock.
20. A term that needs a stat (section 4): flares count only when either side has an IR missile (Turn fighting,
    Missiles and radar, Anti-helicopter), and Anti-helicopter drops the radar warning receiver (no helicopter has a
    radar missile). Both decided gun-only duels: 507 of 4918 RB Anti-helicopter verdicts change (10%); at 9.7 the
    BO 105s (.50-cal pods, no missile) go from 2nd-4th to 6th-8th, below the 20 mm AH-1E.
21. Outgunned only where armor counts, both vehicles below BR 8.7: from the ERA era it compared a shaped charge's
    millimetres (IFV ATGMs, gun-launched ATGMs in `pen`) with a dart's, and set 313 Brawler, 827 Sniper and 224 Ambush
    verdicts at 8.7 and up, mostly against early MBTs. M1 Abrams against BMP-2M in Sniper now stays even (D 0.16, the
    Kornet's 1200 mm made it a disadvantage), against T-90A in Brawler an advantage (D 0.32).
22. Missile carriers (`gl`): no Brawler opponent; a SAM-only one fights no ground vehicle (no Sniper, Flanker or
    Ambush opponent); their `cal`, a missile's diameter, is not compared; their `vel` is their fastest missile's. Read
    as a gun, their launcher made 352 of 545 Brawler candidates lose to SS.11 halftracks and SAM trucks (with the
    filter off the Zachlam Tager led Brawler 6.7 and the RakJPz 2 8.0: now the ST-A3 and the CLOVIS), and their missing
    `vel` was skipped, not lost, so a missile carrier led Sniper RB 8.0 to 9.7 (now OF-40, VT1-2, AMX-32...). A fixed
    launcher's `dep` 0 (Swingfire, Type 60 ATM, LOSAT), which a guided missile does not need, stayed a limit until
    call 36.
23. Torpedo attack: boats and destroyers with torpedoes. With every torpedo carrier, heavy cruisers and capital ships
    led every list from BR 6.0 (IJN Amagi 100 at 8.0 and in Every BR). Now 265 of the 378 carriers; Every BR led by
    PT-20, V-990, IJN Yuudachi; the style's BRs stop at 5.3.
24. Gun brawler reads `fa`, every gun's firepower, and naval `cal` the primary group's: `fm` judged a boat on its
    primary group alone, while its 40 and 20 mm secondary and machine-gun groups do most of a brawl (PGM-9 `fm` 103,
    `fa` 764; 46 of 245 boats had `fm` under half of what their guns of 20 mm and more fire). RB 2.7: Krischan der
    Grosse 7th -> 2nd. `cal` and `fm` now describe the same guns, the game's own trigger groups (section 3's fix 5).
25. Destroyer: `tor` 0.8 -> 0.4, its terms listed heaviest first: a count decisive from 2, it let 16 tubes against 6
    decide a duel alone (Gridley over Verdun). RB 4.0: Z15 1st, then Gridley, Bagley, Helm, Verdun (Gridley was 1st).
26. Rockets and guns on `rkt`, unguided rockets and bombs: `pay` counts ATGMs and AGMs, so all 113 helicopters were
    candidates, 10 with no rocket or bomb at all (HKP3C, Scout AH.Mk.1, Wasp...), and the three BO 105s were scored on
    their HOT or TOW preset, not their rocket pod. `pay` stays as it is on the Vehicles page. Now 103 candidates; the order
    changes in 27 of 94 lists, #1 only between national copies (Mi-24P (Hungary) -> Mi-24P); at RB 9.7 the three
    BO 105s share one second-part score (their 54 kg pod), and at 10.0 the five Mi-24P / Mi-35 copies do.
27. Helicopters' reach in 500 / 2000 m bands, as Close air support's and Anti-aircraft's: the same helicopter / SPAA
    pair was judged on two scales (AH-1F over the M247 in Anti-tank missiles, even in Anti-aircraft). Anti-tank
    missiles applies them to every ground opponent, not only SPAA: 187 of 3683 RB helicopter / SPAA verdicts and about
    120 against other ground vehicles change; the top 5 moves only at 9.0 and 9.7.
28. A multiplied power card is capped at 1.15 x the flight model's figure for all engines at the lightest mass: some
    twins' cards sit above one engine even there, and doubled gave 1.36 x both. 27 aircraft come down (He 219 A-7
    360 -> 305 hp/t, B-24D 280 -> 232, F-82E 440 -> 432); the reference twins stay (B-17G 240, P-38G 400, Me 410 360).
    24 cards kept as they are (factor 1) stay above that figure (Zeppelin 390 against 52.5, GL.832 340 against 161):
    a limit until call 34.
29. `auto` takes one barrel's rate, not the group's: the M50 Ontos's six rifles and about 40 missile and rocket
    launchers were autocannons whose 10-18 s reload was never compared (M50: Sniper RB 6.7 9th -> 20th of 35).
30. A rocket launcher without an ammo set is the main gun of a vehicle whose other weapons are machine guns, judged on
    its rockets (Type 75 MLRS: `pen` 51, `vel` 700, reload 8 s), as the Panzerwerfer 42 and BM-8-24 already were. It
    now beats the IS-3, IS-4M and E-100 in Brawler RB (IS-3: D -0.28, reload 20 against 8 s, traverse, power), and
    25 Ambush RB candidates are only even against it.
31. Brawler, Sniper, Flanker and Ambush rank only what they meet (`self`): with *Only vehicles made for this style* off,
    a vehicle their opponent rule leaves out (missile carriers in Brawler, SAM-only ones in the other three) duels
    nobody and gets no score, listed after the scored rows with *Not made for this style: no duels.* (`bv.noStyle`). It
    was ranked against opponents that never meet it: the Stormer HVM (Starstreak) led Brawler RB 10.7, now the
    Ariete (P), 79. Lists with the filter on are unchanged.
32. A side's flares count only against the other side's IR missiles (`need`, section 4: its `cm` reads 0 when the other
    side has none): flares with nothing to decoy still won the term, Mi-24P against Scout AH.1 crediting the Mi-24P's
    192 flares. A checker counts 76 Anti-helicopter and 78 Missiles and radar verdicts that change (EC-665 Tiger HAC
    against AH-1F: advantage -> even).
33. Missiles and radar picks its Stock candidates on the stock aircraft's missiles (`ir`, `rm`), as Close air support
    does on its loads (call 19): picked on upgraded missiles, jets with none in stock were ranked there with no missile.
    RB 9.0 in Stock: 22 rows -> 7.
34. A propeller aircraft's `pw` is brought within 15% of its flight model's figure, both ways (`fm_power_ratio`,
    section 3's fix 2): call 28's cap covered multiplied cards only, while cards kept as they are strayed as far, above
    and below (Fury Mk II 250 hp/t against 453, Zeppelin 390 against 52.5). 191 aircraft change: Fury Mk II 250 ->
    393.9 hp/t, CW-21 310 -> 465.8, Fokker D.VII 390 -> 265.5, Zeppelin 390 -> 60.4, D.510 310 -> 469.1 (the D.500,
    D.501 and D.371, whose cards copy the Gladiator's, rise too), Hawk III 540 -> 486.1 (still 1st of Energy fighting
    RB 1.0).
35. A preset counts a torpedo tube's torpedoes on any trigger (`preset_composition`): on the gun triggers (`gunner0`,
    `gunner1`, `cannon`, `machine gun`, `additional gun`) every weapon counted one barrel, now only guns do. `tor`:
    L'Intrepide 1 -> 7, S-61 3 -> 4, SUB Tang 5 -> 26; the preset lists now show Kari's 24 Hedgehogs and PG 02's 6
    SRBOC.
36. A fixed launcher (`sy.el` [0, 0]: Swingfire, Striker, Type 60 ATM, LOSAT and SAM launchers, 38 records) has no
    `dep`: its missile steers after launch, and Sniper counted its 0 as no depression (call 22's limit). The BM-13N's
    rails, which rise, keep their measured 0.
37. The user's call: the fighter styles (Turn fighting, Boom and zoom, Energy fighting, Bomber hunting as candidates;
    Missiles and radar's opponents) take every aircraft type, not only the game's class fighter: the game files the
    F-15E, F-15EX, F-15I and F-15IA as strike aircraft. Boom and zoom RB 15.0: F-15EX and F-15IA 95, Golden Eagle 74
    (it was #1 with 81). Bombers and attack aircraft are now listed in those styles too, mostly at the bottom.
38. `ind`, speed lost turning (internal, air): the wing's induced drag factor 1 / (pi x aspect ratio x Oswald efficiency),
    from the flight model (the newer WingPlane block: Span, Areas, FlapsPolar0; the older top-level Wingspan, Areas
    Wing*, Aerodynamics' OswaldsEfficiencyNumber), times `wl`; lower is better, stock follows `wl`. J-10C 84.9,
    Typhoon 86.2, Rafale 94.4, F-16C 62.5, F-15EX 41.6, Spitfire IX 9.4. Asked by the user: the cards' turn time says
    nothing of the speed a delta wing bleeds. On 1360 of 1523 aircraft; drones and a few AI copies have none. Turn
    fighting weighs it 1.0, Energy fighting 0.5. Turn RB 14.7: the J-10C stays #1 (85 -> 73, 5 losses, all to the
    F-16s and F-15s within 1.0); the thrust it would take to sustain the turn is not modelled, only `pwr` beside it.
39. The user's call: a BVR style, beside Missiles and radar (which mixes IR dogfights and radar missiles). RB 14.7:
    the Typhoons 78, JAS39E 74, J-10C 72, Su-30SM 72.
40. The ranking's # column sorts, back to the ranking after another sort (asked by the user).

Left as limits (the wiki page lists them for players):
- the D.500, D.501, D.510 and D.371 cards copy the Gladiator's wing loading and roll (their `pw` too, near their flight
  model since call 34): the D.510 leads Turn fighting RB 1.3;
- the CW-21's card copies the P-40E-1's wing loading (175 kg/m² against its flight model's 124), and the M.B.157's,
  Sakeen's, F-47N's and WM-23's stray too: their `pw` is near the flight model now (call 34), their `wl` is not;
- jet cards share turn time and wing loading across families (the F-4s and F-5Es: 26 s, 303 kg/m²): Phantoms lead Turn
  fighting at 10.0-12.0;
- Close air support has no measure of a gun's anti-tank power: the cannon attackers (Ju 87 G-1/G-2, Hs 129 B-2/B-3,
  IL-2-37, IL-2, Su-6, IL-10) rank last of their lists (follow-up: an internal key for the forward guns' best belt
  penetration at 500 m);
- APKWS and other guided rockets set a helicopter's anti-tank reach (they do outrange SPAA); the Vikhr's proximity fuze
  is not counted against helicopters;
- helicopters' `tw` stays the card's placeholder (the Vehicles page shows it, no duel reads it);
- the GCS-1 seeker (`targetRadiusMin` 30) cannot lock a tank, so it is not in `atg` (F-1, F-4EJ Kai, F-2A);
- the compare dialog's countermeasures (`sy.cm`) ignore modification sets (Eurofighter 32 where the duel reads 352);
- an IFV with an autocannon and ATGMs keeps the autocannon's `vel`; on the Vehicles page a missile carrier's "Muzzle
  velocity" is its missile's top speed (78 playable vehicles);
- the LOSAT's `vel` 1654 m/s is the motor estimate (its card says 1520), and its `kill@2000` reads its `atp` 775 mm, the
  table's 1000 m value (fix 1), where its curve gives 675: a removed vehicle (`ra` 5), hidden by default;
- `main_gun` takes the gunner's (`gunner0`) or the first Weapon block's ammo group, else the largest caliber but none
  under 15 mm: a vehicle left with machine guns under 15 mm has no main gun, so no `cal`, `pen` or `vel` (a gunner's
  launcher of unguided rockets stands in when it has one);
- rocket artillery (Type 75 MLRS, BM-31-12, BM-13N) beats a few heavies (IS-3, IS-4M, E-100, KV-2) in Brawler on
  reload, traverse and power: one more case of the heavies last (calls 1, 30);
- naval stock speed is rounded twice: 133 vessels are 1 km/h off the game's card;
- naval `cal` is the primary group's, as on the game's card: on 21 boats whose biggest gun sits in the secondary group,
  Gun brawler's `cal` and `fa` describe different guns;
- Naval Arcade duels use the Realistic speeds and stock penalty, while the game boosts Arcade engines by ship type
  (boats most) and Arcade torpedoes are faster up close.
