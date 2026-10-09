# Changelog

What changed in each version of WTFTD. Downloads: [Releases](https://github.com/StonewarP/WTFTD-War_Thunder_Full_Test_Drive/releases)
(only the latest version is kept there; each version's code stays available through its git tag).
Versions follow `major.minor.patch`; "beta" until 1.0.

## Unreleased

- **Uninstall** (Settings): remove what WTFTD put on this PC, everything or part by part: the custom vehicle
  files it added to the game, the missions it created, the cache (datamine copy, pictures, maps), the game
  database, your settings and library, and the app itself (WTFTD.exe / WTFTD.app, once it has closed). War
  Thunder itself is never touched. Each part shows its size; a second click confirms.

## 0.16.0 — 2026-10-09

- Map editor: a click on the map itself clears the selection (a drag still moves the map).
- `start.bat` (running from source) no longer keeps a console window open: it starts WTFTD with `pythonw` and
  closes; with options (`--browser`, `--port`…) it keeps the console as before. Messages go to `.cache/wtftd.log`.
- The vehicle + map bar keeps its size when a vehicle or a map is picked.
- **Map editor**: fills the window (4K too), its side panel no longer scrolls sideways. The vehicle picker shows
  every vehicle of the kind, by BR, with the Vehicles menu's filters: nations, rank, battle rating
  (its AB / RB / SB mode), type.
- Fix: an AI unit's Configure from the Maps window left that window over the vehicle panel; it now steps aside and
  comes back when the editor closes.
- New cheat **Super mobility** (custom vehicles): ground vehicles get engine power ×4, top speed ×2, brakes ×3;
  aircraft roll, pitch and turn much faster (less inertia, bigger and quicker controls, more lift), half the drag,
  engine power / thrust ×3 and 40 % less weight. A value set under Modifications wins.
- Fix: the **Thrust** modification of jets did nothing (the game takes their maximum thrust from the flight
  model's thrust table, which it now scales).
- **Invulnerable**: AI aircraft now attack you too (it used the game's spawn protection, which they respect).
- New cheat **Unbreakable airframe** (aircraft, helicopters, custom vehicles): no wings torn off by overspeed or g
  (Mach limit included), gear, flaps and canopy don't break.
- **Mission description** (mission options): shown under the mission in the game's list (it showed
  "missions//objective").
- **Map editor**: the vehicles the scenario brings into its zones show as markers (triangle: aircraft,
  square: ground, diamond: ships, dashed white outline) at every zoom; zone outlines are off by default
  (Zones button), drawn at their real size (too small to see: left out), and hiding them keeps those markers.
  Clicking a unit in the list brings it into view and highlights it alone (a unit the scenario places in game:
  the zones it may appear in). **Vehicles by BR**: every enemy, ally or selected unit gets a vehicle of its own
  kind (fighter, bomber, tank, SPAA…) from the research trees at the BR closest to your vehicle's or to a BR
  you choose, from the nations you tick (one, several or all, in turn). With your vehicle's BR, those units **follow your vehicle**: take
  another one and they get vehicles near its BR (when the editor opens and when the mission is created); a
  vehicle picked by hand for a unit stops it following.
- **Template units can change vehicle**: the units a scenario takes from a game template it imports directly (the
  targets of the test flights) get the vehicle picker, a loadout and Vehicles by BR. The mission then declares
  that template's units itself; the templates' scripts stay imported as the game wrote them (the data keeps the
  templates: it is rebuilt once). Units of nested templates (the bases' AA) keep their vehicle.
- **Vehicles by BR → Fire: Attacks**: the units it sets also fire at you (test flight and test drive targets are
  passive). Template units set to Attacks in the editor now stay so: the templates' scripts made them passive
  again when they respawned them, WTFTD sets them back every 3 s.
- **Vehicles by BR** only picks vehicles that fire on their own (not a SAM battery's radar or launcher: AI ones
  don't fire); with Fire: Attacks, enemy aircraft also hunt you. Template units hunting you are told again every
  10 s (their scripts bring them in later, on a route of their own).
- **Hunts me**: the order is given again every 10 s for every unit (at mission start you may not be there yet: on
  test flights the game's scripts spawn you a moment later and the order was lost).
- **Test flights**: the targets and airfield follow your vehicle's rank (high from rank V), as when the game starts
  them from the hangar (a user mission kept the low ones: a dirt strip).
- The map settings' **Training targets** (scenario / my BR / a BR) are gone: Vehicles by BR in the map editor
  replaces them (nations, allies and added units too, follows your vehicle).
- **Map editor**: **right click** on the map: the useful actions right there (on a unit: loadout, side,
  movement, copy, duplicate, remove; on the map: paste here, add a ground unit / aircraft / ship here, start
  here, centre). **Paste** drops the copied units centred on the pointer; the Paste button
  lets them follow the pointer until a click places them. **Cancel** next to Done puts the map back as it was
  when the editor opened.
- **Map editor**: zones say what the scenario puts there (your start, the vehicles it brings in, with
  pictures) and are coloured by side; the map is shaded, labels sit on dark pills, a tip names whatever is
  under the pointer, scenery can be hidden. **Several units at once**: Ctrl / Shift + click or Shift + drag
  to select, then change side, vehicle, count, fire, movement, altitude or speed for all; drag them together;
  Ctrl+C / Ctrl+V / Ctrl+D copy, paste and duplicate; each click can place up to 20 units side by side.
  **Vehicle picker with pictures**, and **My vehicles**: a saved vehicle becomes an AI unit, its loadout
  included. **AI loadouts**: Configure opens the unit in the vehicle panel (loadout, ammo) as for your own
  vehicle; aircraft with custom pylons get a custom aircraft of their own.
- **Ground starts without a jump**: on test flights you are parked on a runway of your own at the start set
  in the editor; on tank test drives the scenario's respawn point follows your start. Templates that never
  move you no longer get the extra respawn.
- **Map editor**: the scenario's **zones** show on the map (those its scripts use, to spawn, respawn or send
  units, highlighted) and can be moved: what the game puts there moves with them. **Your start**: on the
  ground or in the air, altitude, speed and compass heading (an arrow on the map, its tip can be dragged); it
  holds even when the scenario's templates respawn you in a zone of theirs, after a crash too. On test flights, an air start moves and turns
  the scenario's own start zone: you spawn there straight away, no jump. These left
  the vehicle panel (its last step keeps the fuel) and the map window. Template units can be made to
  **attack** too (not only "never shoots").
- The map editor no longer shows units that never appear: units the scenario keeps delayed (an AV-8B on
  Afghanistan) are "placed in game", template ships are dropped on maps without water.
- Fix: the map editor drew the units of the game templates a scenario imports at the template's own
  coordinates, which mean nothing on that map (Afghanistan: off the map, far from where they appear). WTFTD
  now follows the scenario's scripts across the whole import chain: units moved to a known zone show there,
  units the game places while the mission runs (asleep at start, zone picked by a variable, often at random)
  are listed as "placed in game" and not drawn.
- The flares / chaff counts follow the slider live.
- **All the game's maps**: the Maps tab shows the test-drive maps, then the game's 131 other maps.
  On those, a bare start (you alone, no targets) for each kind of vehicle the map suits, placed where the
  game's own missions (battles, training…) put that kind of vehicle; aircraft start in the air. Add targets
  with Edit on the map. Ground, air and naval starts checked in game.
- **Your library**, three tabs, everything shareable (code or .wtftd file, imported into the right tab):
  **My maps** (saved map variants), **My vehicles** (saved vehicle setups: Choose puts one in the bottom bar
  without opening it) and **My missions** (vehicle + map pairs saved with the bar's save button, ready to
  Choose or Create, and the mission files created in the game). Old share codes import as missions.
  Tabs follow the bar: Vehicles · My vehicles · Maps · My maps · My missions · Weapons. The vehicle filters
  show in Vehicles and My vehicles only (and filter both); the vehicle + map bar shows in the four first tabs.
- **Vehicle + map**: a new **Maps** tab shows every map (the game's own tactical map as picture). Click one:
  a window lists its variants (scenarios), to choose one or edit it on the map (move, add, remove units) as
  in the vehicle panel, even before picking a vehicle. A bar at the bottom holds the vehicle and the map of
  the mission, picked in any order, and creates it. Edited variants can be **saved** under a name (Save…), then
  chosen again with any vehicle, edited, updated, renamed or deleted (`user/variants.json`).
- The map's settings moved from the vehicle panel to the map window: enemy units (as in the scenario / don't
  shoot back / shoot), time of day, weather and start heading. They go
  with any vehicle and are kept in saved variants. The vehicle panel no longer has a Map & scenario step;
  **Save setup** keeps the vehicle's own setup (loadout, ammo, modifications, cheats, start) for any map.
- The vehicle panel's main button is **Select vehicle** (puts it in the bottom bar); **Create mission** is in the
  bar only. Opening panels just browses: each vehicle keeps its own setup, and the mission uses the selected
  vehicle's. Loading a saved setup or a mission selects its vehicle.
- Mission type, title and file name moved to a **Mission** window (gear of the bottom bar): they belong to
  the vehicle + map. Title and file name stay automatic until changed, and a custom one only applies to the
  vehicle and map it was written for. The picked map and its edits follow from one vehicle to
  the next when it suits it; a vehicle opened again keeps its setup.
- **Ammunition icons**: shells, aircraft / helicopter / ship belts and flares / chaff show the game's own
  icons (from its icon table, so they follow game updates). The game data rebuilds itself once at first launch.
- **Flares / chaff split**: for countermeasure launchers that take both, choose how many of each (the sum is
  the launcher's capacity). Checked in game on the F-14B, MiG-29SMT and Su-25.
- Fix: aircraft ammo slots are written the way the game spawns aircraft (each tagged with its weapon),
  with countermeasure counts per launcher: flares / chaff were ignored on some aircraft (F-14B, Su-25).
  Reloading a mission with mixed flares / chaff no longer shows empty counts.
- Fix: with "Invulnerable" on, some aircraft (MiG-29SMT) could not take off: the repair applied every second
  restarted their engines. Aircraft and helicopters now stay invulnerable without it. Re-create older
  aircraft missions to get the fix.
- **Targets shoot** (map settings): the scenario's enemies that hold their fire (test-drive targets) fire at
  will, to test invulnerability and countermeasures. Units set in the map editor keep their setting.
- Loadout: aircraft with fixed presets only (most low-BR aircraft) show them as a grid laid out like the
  game's hangar (13 columns, heaviest weapons in the middle), with the weapons' icons. Preset names read
  like the game's ("SC50 ×4"). (Weapon masses added to the game data.)
- **Custom loadout for fixed-preset aircraft** (custom vehicles): the grid switches to one column per
  attachment point found in the aircraft's presets; mix the official weapons or put any weapon of the game on
  a point. Written as a preset of plain weapons, like the game's own. Beta, see `docs/ingame-checklist.md`.
- First launch: the language picker no longer overlaps the logo; the progress bar shows a translated step
  instead of the English log (the log appears only on error).
- Opening a vehicle: every setup step starts closed.
- Fix: the app could start half-broken (comparison and weapons page not wired up) when the local server
  answered faster than the browser loaded its last scripts.
- The app window no longer offers to translate the page (Edge ignored the old setting).
- Fix: My missions shows the right vehicle (picture, name, Load) for missions saved under a custom file name.

## 0.15.0 — 2026-10-08

- **macOS**: WTFTD runs on macOS too. It finds War Thunder (Steam or standalone, inside
  `WarThunderLauncher.app`), launches it, and opens the UI in a Chrome / Edge / Brave app window. It quits
  when the window closes. Data lives in `~/Library/Application Support/WTFTD`. Git comes from Homebrew or
  Apple's Command Line Tools. Oodle runtimes are `liboo2core*.dylib`.
- Releases also ship `WTFTD-macOS.zip` (WTFTD.app, Apple silicon), built by GitHub Actions with its SHA-256;
  `build_app.sh` / `start.command` build / run it locally.
- Tests run on Linux, Windows and macOS.
- Fix: release notes lost their line breaks when GitHub Actions added the exe's SHA-256, so the whole text
  showed as one big heading. The macOS zip's SHA-256 is now always added too.

## 0.14.4 — 2026-10-08

- The exe is built by GitHub Actions from the released code and published with its SHA-256, so anyone can
  check that a download matches the source.
- Automated tests (BLK format, weapon stats, custom-vehicle file safety, local server) run on every change.
- Fix: BLK files with a comment after a value on the same line (`a:i=1 // note`) couldn't be read.
- FAQ in the README; CONTRIBUTING, SECURITY and this changelog.

## 0.14.3 — 2026-10-08

- Security: the local server refuses data reads that don't come from WTFTD's own page (a malicious website
  could in theory read settings, saved setups and the game folder path through DNS rebinding).
- Ko-fi "Sponsor" button on the repository page.

## 0.14.2 — 2026-10-08

- Weapons page: **nuclear bombs** category — yield from the game files (5 kt to 1.6 Mt), burst height,
  "raw power" and "yield per kg" rankings. The ground battles' killstreak nukes (Mark 6, Mark 7…) are
  listed with an "Instant win" badge (the game gives them no yield).

## 0.14.1 — 2026-10-08

- IRCCM: both mechanisms are detected — flare rejection (AIM-9M) and narrow tracking gate (R-73, Magic 2,
  R-27T…), which was missed — graded and explained in the badge.
- Speeds: ~130 rockets and ATGMs had none, and recent missiles (AIM-54…) showed the game's speed cap:
  speed now comes from the motor (thrust, burn time, mass), capped by the game's limits.
- Radar missiles' "Close range" ranks by max G, lock angle and the new *Acceleration off the rail*.
- Penetration: only HEAT or kinetic; high-explosive warheads no longer show their fragments' penetration.
- Mavericks, RB 75, GROM and other heavy guided missiles moved from *Anti-tank* to *Air-to-surface*.
- Scores: 100 = the best weapon of the category, in the table and in the comparison.

## 0.14.0 — 2026-10-08

- **Weapons page**: ~860 missiles, bombs, rockets and torpedoes from the game files, by category, with
  stats, "best for" rankings, a guide per category, community notes, comparison and carriers.
- **Stock / All upgrades** switch on vehicle stats and in the vehicle comparison.
- Filter by **vehicle type** (light / heavy tank, fighter, bomber…); **sort by rarity** with badges.
- Language picked from Windows on first launch, and selectable on the welcome screen.
- Ko-fi support button (top bar and Settings).
- Fix: heavy tanks, wheeled vehicles and some ships (≈250) were hidden as non-playable.

## 0.13.0 — 2026-10-08

- **Compare up to 5 vehicles** side by side: BR, every stat (best highlighted), guns, shells, pylon weapons.
- **New version alert**: the app checks the releases and shows a *New version* button.
- *Report a bug* / *Suggest an idea* from Settings, with GitHub issue forms.

## 0.12.0 — 2026-10-08

- **Share a setup**: a short code to paste or a `.wtftd` file; a friend imports it and gets the same mission.

## 0.11.0 — 2026-10-08

- **Weapon picker** with the game's icons: find vehicles carrying given missiles, bombs, guns or shell types.
- Layout for smaller screens; aircraft stats name power-to-weight (propeller) vs thrust-to-weight (jet).

## 0.10.0 — 2026-10-08

- **Vehicle stats** on each card (speed, power-to-weight, armor, traverse, penetration, reload, turn time,
  climb…), sort by any stat, min / max filters, search by weapon.
- MIT license.

## 0.9.0 — 2026-10-08 — first public beta

- Test drive any vehicle (ground, aircraft, helicopters, boats, ships) in the official Test Drive / Test
  Flight scenarios and hangar maps, as a user mission.
- Vehicle browser (grid and research trees, wiki images), loadouts (pylon editor, non-standard weapons,
  nuclear bombs), ammunition, modifications, cheats, conditions, training targets.
- Custom vehicles through the CDK `userVehicles` mechanism, to drive vehicles you don't own.
- Scenario editor on the level's real tactical map with ground heights.
- 11 languages; Windows exe; game data built on first launch from the community datamine (progress bar),
  updated automatically after game patches.
