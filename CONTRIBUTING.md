# Contributing to WTFTD

Thanks for helping! Bug reports, ideas, translation fixes and code are all welcome.

- **Bugs and ideas**: open an [issue](https://github.com/StonewarP/WTFTD/issues/new/choose) (use the forms).
  For a bug, paste your setup's **share code** (Saved setups → Share): it lets us rebuild your exact setup.
- **Questions**: ask in [Discussions](https://github.com/StonewarP/WTFTD/discussions).
- **Security problems**: don't open a public issue, see [SECURITY.md](SECURITY.md).

## Run from source

Windows 10/11 or macOS, Python 3.10+ — no extra package needed (standard library only).

```bash
git clone https://github.com/StonewarP/WTFTD.git
cd WTFTD
python -m wtftd
```

The first launch downloads the game data (≈1 GB from the community
[War Thunder datamine](https://github.com/gszabi99/War-Thunder-Datamine)) into `.cache/` and builds `data/`.
Rebuild the data by hand with `python -m wtftd.builder --no-pull` (without downloading) or
`python -m wtftd.builder` (with an update).

`python -m wtftd --browser` opens the app in your default browser, handy with the browser's developer tools.

## Code layout

| Path | What it does |
|---|---|
| `wtftd/server.py` | Local HTTP server and API (127.0.0.1 only) |
| `wtftd/builder.py` | Datamine → `data/*.json` (vehicles, scenarios, trees, translations) |
| `wtftd/armament.py` | Weapons page data (missiles, bombs, rockets, torpedoes) |
| `wtftd/mission.py` | Official scenario + your setup → `.blk` user mission |
| `wtftd/cdk.py` | Custom vehicle files (`userVehicles` + `@override`) |
| `wtftd/blk.py` | BLK text format writer / reader |
| `web/` | UI: plain HTML / CSS / JavaScript, no build step |
| `web/locales/` | UI translations |
| `tests/` | Automated tests |

When a change adds fields the app needs to `data/*.json`, bump `SCHEMA` in `wtftd/builder.py`: installed data
is then rebuilt automatically.

## Tests

```bash
python -m unittest discover -s tests -t .
```

They run on GitHub for every push and pull request. Tests that need the real game files
(`tests/test_game_data.py`) only run on a PC where the datamine has been downloaded. Add a test with any fix
to the data extraction: a reference value from the game files is enough.

## Translations

UI texts live in `web/locales/<code>.json`; `en.json` is the reference. Vehicle, weapon and map names come
from the game's own translations and don't need translating.

- **Fix a wording**: edit the file on GitHub (pencil icon) and propose the change, or open a *Suggestion*
  issue with the key and the correct text.
- **Add a language**: copy `en.json` to `<code>.json`, translate the values (keep the keys and the
  `{placeholders}`), and add the language to `web/locales/index.json`.

## Pull requests

- One topic per pull request, with a short description of what changes for the player.
- Match the style of the surrounding code; no new dependencies (the app is standard-library Python and plain JS).
- UI text: English in `en.json`, plus the other languages if you can (otherwise English is used as fallback).
- Never commit game files (`data/`, `.cache/`) or anything from your `user/` folder.

## Releases

1. Bump `__version__` in `wtftd/__init__.py` and add the version to `CHANGELOG.md`.
2. Commit, push, then publish a release with the tag `v<version>-beta` (notes = the changelog entry).
3. GitHub Actions builds `WTFTD.exe` and `WTFTD-macOS.zip` from that tag and attaches them to the release with
   their SHA-256.
