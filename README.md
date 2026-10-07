# WTFTD — War Thunder Full Test Drive

A local app to test drive **any** War Thunder vehicle (ground, aircraft, helicopters, boats, ships)
with the loadout, ammunition, map and conditions you choose.

It takes an **official Test Drive / Test Flight mission** from the game files (with its targets,
triggers and respawn logic), swaps in your vehicle and loadout, and writes it to
`War Thunder/UserMissions/`. In game: **Single missions → User missions**.

## Start

Double-click **`start.bat`** (needs Python 3.10+, no extra packages).
The app opens in its own window (Edge/Chrome app mode) and stops when you close it.

```bash
python -m wtftd             # app window
python -m wtftd --browser   # use the default browser instead
```

## Features

- 3,500+ vehicles with images from the [War Thunder wiki](https://wiki.warthunder.com/) (cached in `.cache/img`)
- Filters: type, nation, rank, BR (AB/RB/SB), favorites, premium/event, non-playable units
- **Maps:** the 79 official test drive / test flight scenarios (firing range, Fulda, naval range, airfields, heli ranges…)
- **Loadout:** every official weapon preset, with its weapons listed (R-60M ×6, S-5KP ×128…)
- **Ammo:** 4 shell slots with round counts for tanks; belts per gun for aircraft, helicopters and ships (plus flares/chaff)
- Conditions: time of day, weather, air start with altitude/speed for aircraft
- **Scenario editor**: top-down map of the scenario — replace / remove enemies, add ground, air or naval
  units, set them still, aggressive, return-fire or passive, or make them hunt you; move your start
- **Hangar maps** (menu background: regular, winter, Halloween, Lunar New Year, anniversary) as scenarios
- **Pylon editor** laid out like the game's (presets as rows, pylons as columns, game icons): pick each
  pylon's weapon by category, or turn on **non-standard weapons** to mount any of the game's ~2,300
  air weapons (missiles, bombs, rockets, torpedoes, pods…), with a warning when the aircraft lacks
  the radar / laser designator / guidance system the weapon needs
- **Nuclear bombs** on any aircraft / helicopter (custom vehicles): RN-28, RN-40, B61, AN-52, KB-1, RDS-4, RDS-37
- **Training targets**: keep the scenario's targets, match your BR, or pick a BR — enemy units are
  swapped for vehicles of the same type at that level, mixed across nations (60 of 79 scenarios)
- **Cheats**: invulnerable (with custom vehicles: damage model ×1000; otherwise instant repair/respawn),
  unlimited ammo, no reload, unlimited fuel, auto repair/rearm, passive targets, no collisions,
  expert crew. A hint lists the active cheats when the mission starts.
- Dark / light theme (or same as Windows), research-tree view per nation, sticky filters
- Saved setups, list of generated missions, `.blk` preview, launch War Thunder (Steam or standalone)

## Custom vehicles (on by default)

War Thunder only opens a user mission if you own its vehicle. With **custom vehicles** enabled
(Settings), WTFTD uses the game's `userVehicles` mechanism (from the CDK, popularised by Ask3lad):

- the mission uses `unit_class:t="userVehicles/<host>"`, where `<host>` is a vehicle you own
  (US reserve vehicles by default: M2A4, P-26A-34 M2, PT-6, USS Litchfield — helicopters have no
  reserve, pick one you own);
- WTFTD writes `War Thunder/content/pkg_local/gameData/.../userVehicles/<host>.blk`, which `include`s
  the real vehicle and applies your **modifications** with `@override:` lines:
  engine power/RPM, mass, brakes, top speed, turret speeds, ammo capacity, reload, shell velocity /
  mass / explosive / HEAT penetration / APFSDS rod length; for aircraft: mass, fuel, thrust, boosts and
  **pylon-by-pylon loadouts**.

Rules: only new files are written (never a path that replaces a game file), every file is listed in
`user/cdk_manifest.json`, and **Settings → Remove custom vehicle files** deletes them (do it before
playing online if you want a clean install). One custom vehicle per type at a time: the last mission
you create defines it. Ground vehicles follow the known-working method; aircraft, helicopters and
ships are experimental. This is not endorsed by Gaijin — use at your own risk.

## Game data & automatic updates

Every 3 hours (and at start-up) WTFTD checks the datamine's published game version. When the game is
patched, it rebuilds its database in the background (new vehicles, loadouts, scenarios); a banner
shows progress and offers to reload. New vehicles' wiki images are fetched on first view and cached
in `.cache/img`. Turn this off in Settings ("Update automatically").

`data/` is generated from the community datamine
([gszabi99/War-Thunder-Datamine](https://github.com/gszabi99/War-Thunder-Datamine)).
After a game patch: **Settings → Update game data** (needs [Git](https://git-scm.com); first download ≈1 GB into `.cache/datamine`), or:

```bash
python -m wtftd.builder
```

## Translations

UI text lives in `web/locales/<code>.json`. To add a language:

1. Copy `web/locales/en.json` to e.g. `web/locales/fr.json` and translate the values (keep the keys and `{placeholders}`).
2. Add `{ "code": "fr", "name": "Français" }` to `web/locales/index.json`.
3. Pick it in **Settings → Language**.

Vehicle, weapon, ammo and map names are already translated in all 20 game languages (`data/lang/`) and
follow the selected language automatically.

## Known limits

- Without custom vehicles, aircraft use the official presets and the vehicle must be owned.
- For aircraft and ships, belts are matched to gun groups in order (best effort).
- "Non-playable units" come from the game files (AI, removed, unreleased) and may not load or may behave oddly.

## Layout

```
start.bat            launcher
wtftd/               Python backend (stdlib only)
  server.py          local HTTP server + API (127.0.0.1 only)
  mission.py         official scenario + your setup -> .blk mission
  cdk.py             custom vehicle files (userVehicles + @override modifications)
  blk.py             BLK text writer/parser
  builder.py         datamine -> data/*.json
  game.py            install detection, launching
web/                 UI (HTML/CSS/JS, no build step)
data/                generated game database
user/                your settings and saved setups
```
