# Security

## Reporting a problem

Please **don't open a public issue** for a security problem. Report it privately: on this repository, go to
**Security → Report a vulnerability** (GitHub's private vulnerability reporting). Describe what you found,
how to reproduce it and what it allows; you'll get an answer as soon as possible, and credit in the release
notes if you wish.

Only the latest release is supported: fixes ship in a new version.

## What WTFTD does on your PC

- **Local server only.** The app runs a small web server on `127.0.0.1` (never reachable from the network).
  It only answers WTFTD's own page: requests from other websites are refused.
- **Files it writes:**
  - `%LOCALAPPDATA%\WTFTD` on Windows, `~/Library/Application Support/WTFTD` on macOS (or the source folder):
    settings, saved setups, game database, image cache;
  - `War Thunder\UserMissions\`: the missions you create;
  - with custom vehicles on: new files under `War Thunder\content\pkg_local` and `content\pkg_user` only —
    never a path that replaces a game file. Every file is listed in `user\cdk_manifest.json` and
    *Settings → Remove custom vehicle files* deletes them.
- **What it downloads:** the community [War Thunder datamine](https://github.com/gszabi99/War-Thunder-Datamine)
  (with your Git, or the official portable MinGit from git-for-windows), vehicle images from the
  [War Thunder wiki](https://wiki.warthunder.com/), and the release list of this repository (new version alert).
- **What it sends:** nothing. No account, no telemetry, no analytics.
- **The apps** (WTFTD.exe, WTFTD-macOS.zip) are built by GitHub Actions from the released source code; each
  release lists their SHA-256 (check with `Get-FileHash WTFTD.exe` in PowerShell or
  `shasum -a 256 WTFTD-macOS.zip` in Terminal). They aren't code-signed yet, hence the SmartScreen / Gatekeeper
  warnings.
