# Changelog

What changed in each version of WTFTD. Downloads: [Releases](https://github.com/StonewarP/WTFTD-War_Thunder_Full_Test_Drive/releases)
(only the latest version is kept there; each version's code stays available through its git tag).
Versions follow `major.minor.patch`; "beta" until 1.0.

## Unreleased

- **Ammunition icons**: shells, aircraft / helicopter / ship belts and flares / chaff show the game's own
  icons (from its icon table, so they follow game updates). The game data rebuilds itself once (schema 8).
- **Flares / chaff split**: for countermeasure launchers that take both, choose how many of each (the sum is
  the launcher's capacity). Checked in game on the F-14B, MiG-29SMT and Su-25.
- Fix: aircraft ammo slots are written the way the game spawns aircraft (each tagged with its weapon),
  with countermeasure counts per launcher: flares / chaff were ignored on some aircraft (F-14B, Su-25).
  Reloading a mission with mixed flares / chaff no longer shows empty counts.
- Fix: with "Invulnerable" on, some aircraft (MiG-29SMT) could not take off: the repair applied every second
  restarted their engines. Aircraft and helicopters now stay invulnerable without it. Re-create older
  aircraft missions to get the fix.
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
