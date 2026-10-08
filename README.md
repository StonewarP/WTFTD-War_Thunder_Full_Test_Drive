# WTFTD — War Thunder Full Test Drive

> **Beta** — it works, but some features are still untested in game (see *Known limits*). Feedback and bug
> reports are welcome in the issues.

Test drive **any** War Thunder vehicle — ground, aircraft, helicopters, boats, ships — with the
loadout, ammunition, map, targets and conditions you choose, even vehicles you don't own.

WTFTD takes an **official Test Drive / Test Flight mission** from the game files (with its targets,
triggers and respawn logic), puts your vehicle and setup in it, and writes it to
`War Thunder/UserMissions/`. In game: **Single missions → User missions**.

![Vehicle browser](docs/screenshots/01-browse.png)

## Download

**[⬇ Download WTFTD.exe](https://github.com/StonewarP/WTFTD/releases)** (Windows 10/11) —
nothing to install: double-click it, the app opens in its own window and finds your game by itself
(Steam or standalone). Close the window to quit.

- **First launch**: WTFTD downloads the game data once (≈1 GB from the community
  [War Thunder datamine](https://github.com/gszabi99/War-Thunder-Datamine), 2–5 minutes) and builds its
  database on your PC. No game data is shipped with WTFTD. If Git isn't installed, the official portable
  MinGit (git-for-windows) is fetched automatically. The data then updates itself after each game patch.
- Your settings, missions and the game database live in `%LOCALAPPDATA%\WTFTD`.
- The exe is not code-signed: if Windows SmartScreen warns you, click **More info → Run anyway**.

## How it works

1. **Pick a vehicle** in the list or in the research trees (filters by type, nation, rank, BR…).
2. **Set it up** step by step: map & scenario, loadout, ammunition, modifications, cheats, conditions.
3. **Create mission**, start War Thunder (button in the app), open *Single missions → User missions*.

| Stats: tanks over 60 km/h, best turret armor first | Search by weapon (AIM-9L), fastest first, vehicle stats |
|---|---|
| ![Stats filters](docs/screenshots/07-stats.png) | ![Weapon search and stats](docs/screenshots/08-stats-drawer.png) |

| Research trees | Pylon editor — here a B61 nuclear bomb on pylon 5 |
|---|---|
| ![Research tree](docs/screenshots/02-tree.png) | ![Pylon editor](docs/screenshots/03-pylons.png) |

| Scenario editor on the real map, with ground heights | Your real spawn (runway) and targets at your BR |
|---|---|
| ![Scenario editor](docs/screenshots/05-editor.png) | ![Runway spawn](docs/screenshots/06-editor-air.png) |

![Conditions: air start, fuel load](docs/screenshots/04-conditions.png)

## Features

- **3,500+ vehicles** with images from the [War Thunder wiki](https://wiki.warthunder.com/), grid or
  research-tree view, filters (type, nation, rank, BR in AB/RB/SB, favorites, premium/event, non-playable units)
- **Stats & fine search**: each vehicle's performance — top / reverse speed, power-to-weight, engine power,
  turret / hull armor, turret traverse, gun caliber, HEAT penetration, reload; for aircraft turn time, roll rate,
  climb rate, ceiling, thrust-to-weight, wing loading; for ships displacement — shown on its card, **sortable**
  (fastest, best turning, best armored…) and **filterable with min / max** values. **Search by carried weapon or
  ammunition** (e.g. `AIM-9L`, `DM53`, `B61`; several terms with `,`)
- **100+ official scenarios**: firing range, Fulda, naval range, airfields, heli ranges, carriers,
  seaplane bases… plus the **hangar maps** (regular, winter, Halloween, Lunar New Year, anniversary)
- **Loadout**: every official preset, or a **pylon editor** laid out like the game's (presets as rows,
  pylons as columns, game icons). Turn on **non-standard weapons** to mount any of the game's ~2,300 air
  weapons on any pylon — missiles, bombs, rockets, torpedoes, pods, and **nuclear bombs** (RN-28, RN-40,
  B61, AN-52, KB-1, RDS-4, RDS-37) — with a warning when the aircraft lacks the radar / laser designator /
  guidance the weapon needs
- **Ammunition**: 4 shell slots with round counts for tanks; belts per gun for aircraft, helicopters and ships
- **Modifications** (custom vehicles): engine power, mass, top speed, brakes, turret speed, thrust,
  reload, ammo capacity, shell velocity / mass / explosive / penetration…
- **Scenario editor** on the level's real tactical map, read from the game files:
  - drag any unit (and your start) to move it — ground units are put **on the ground** using the map's heightmap;
  - add ground, air or naval units as **allies or enemies**, remove units, swap their vehicle;
  - behaviour: still, aggressive, return fire or passive; enemies can **hunt you**, allies can **escort you**;
  - shows where the scenario really spawns you (runway / start area) and the units it teleports
- **Training targets**: keep the scenario's targets, match your BR, or pick a BR — enemies are swapped for
  vehicles of the same type at that level, mixed across nations
- **Conditions**: time of day, weather, air start with altitude / speed, **fuel load** (% of the tanks)
- **Cheats**: invulnerable, unlimited ammo, no reload, unlimited fuel, auto repair / rearm, passive
  targets, no collisions, expert / ace crew
- **11 languages**: English, Français, Deutsch, Русский, Polski, Español, Português, Italiano, Čeština,
  简体中文, 日本語 — vehicle, weapon and map names follow the game's own translations. UI translations
  other than English were machine-assisted and may contain mistakes: corrections are welcome
- Dark / light theme, saved setups, list of generated missions, `.blk` preview, launch War Thunder

## Custom vehicles (on by default)

War Thunder only opens a user mission if you own its vehicle. With **custom vehicles** (Settings),
WTFTD uses the game's `userVehicles` mechanism (from the CDK, popularised by Ask3lad):

- the mission uses `unit_class:t="userVehicles/<host>"`, where `<host>` is a vehicle you own (US reserve
  vehicles by default: M2A4, PT-6, USS Litchfield — helicopters have no reserve, pick one you own).
  Aircraft get their own new file in `content/pkg_user` and need no host;
- WTFTD writes files that `include` the real vehicle and apply your **modifications** and
  **pylon-by-pylon loadouts** with `@override:` lines.

Rules: only new files are written (never a path that replaces a game file), every file is listed in
`user/cdk_manifest.json`, and **Settings → Remove custom vehicle files** deletes them (do it before
playing online if you want a clean install). One custom vehicle per type at a time: the last mission you
create defines it. This is not endorsed by Gaijin — use at your own risk.

## Map backgrounds & ground heights

The editor draws the level's tactical maps (full map + detailed ground-battle map) straight from the
game's texture packs (`content/base/res/*.dxp.bin`). They are Oodle-compressed: WTFTD uses the official
Oodle runtime (`oo2core_<n>_win64.dll`, version 6+) that many other games ship (Battlefield, Call of Duty,
Cyberpunk…) — it is found automatically in your Steam / Epic / game folders, or set it in **Settings**.
Ground heights come the same way from the level's heightmap (`levels/<map>.bin`, ground-battle maps);
older air maps have no heightmap and heights are estimated there. Without Oodle, a scenario's map is
captured from the game (localhost:8111) the first time you play it with WTFTD open.

## Run from source

Needs Python 3.10+ (no extra packages). Double-click **`start.bat`**, or:

```bash
python -m wtftd
```

`python -m wtftd --browser` uses your default browser instead of an app window.

To build `dist\WTFTD.exe` yourself, run **`build_exe.bat`** (installs PyInstaller in `.cache\build-venv`).

## Game data & automatic updates

The game database (`data/`, not in this repository) is generated on your PC from the community datamine
([gszabi99/War-Thunder-Datamine](https://github.com/gszabi99/War-Thunder-Datamine)): first download ≈1 GB
into `.cache/datamine`, with your Git or an automatically fetched MinGit. Every 3 hours (and at start-up)
WTFTD checks the datamine's game version and rebuilds after a patch. Manual update: **Settings → Update
game data**, or `python -m wtftd.builder`.

## Translations

UI text lives in `web/locales/<code>.json`. The non-English files were machine-assisted: native speakers'
corrections are very welcome (pull request or issue). To add a language: copy `en.json`, translate the
values (keep the keys and `{placeholders}`), and add it to `web/locales/index.json`.

## Known limits

- Stats come from the game's own stat cards (aircraft, armor) or are computed from the vehicle files (tank top
  speed from the gearbox, ±10 %). Kinetic (AP / APFSDS) penetration isn't stored in the game files and isn't shown.
- Without custom vehicles, aircraft use the official presets and the vehicle must be owned.
- For aircraft and ships, belts are matched to gun groups in order (best effort).
- A few scenarios pick their spawn / enemies from your vehicle's nation (Mozdok heli / UCAV, Denmark
  hydrobase); the editor shows their default branch.
- "Non-playable units" come from the game files (AI, removed, unreleased) and may not load or behave oddly.

## Layout

```
start.bat / build_exe.bat   run from source / build WTFTD.exe
wtftd_app.py                entry point of the exe
wtftd/                      Python backend (stdlib only)
  server.py                 local HTTP server + API (127.0.0.1 only)
  mission.py                official scenario + your setup -> .blk mission
  cdk.py                    custom vehicle files (userVehicles + @override modifications)
  maptex.py / terrain.py    tactical maps and heightmaps from the game files
  builder.py                datamine -> data/*.json
  blk.py, game.py, paths.py BLK writer, install detection, file locations
web/                        UI (HTML/CSS/JS, no build step), web/locales = translations, stats.js = stats & search
data/                       game database, generated on first launch (not versioned)
docs/screenshots/           README images
```

## License

[MIT](LICENSE) — free to use, modify and share, keeping the copyright notice. War Thunder and its data belong
to Gaijin Entertainment; WTFTD is a fan-made tool, not affiliated with or endorsed by Gaijin.
