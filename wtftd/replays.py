"""My battles: the player's own results, from the replay files the game saves (<game>/Replays/*.wrpl).

Read only, and only two parts of a file: its fixed header and the results at its end, never the recording in between.
The results hold all the players of a battle: only the author's own name, squadron tag and numbers are kept, nobody else's.
Each file is read once: the index (.cache/battles.json) remembers its row by size and date.
One exception, the player's own request: a teammate who shot the player down is kept by name (teamkills).

What a replay can't tell:
  - the result of a battle left before the end: the game writes it only at the end (no status: "left");
  - which vehicle made which kill, in a battle with several: the numbers are the whole battle's."""
from __future__ import annotations

import os
import re
import struct
import time
from pathlib import Path

from . import battle, vromfs

VERSION = 2  # of the rows in the index: another one reads every file again
MAGIC = b"\xe5\xac\x00\x10"
HEADER = 1096  # the fixed fields end with the battle class
RESULTS_MAX = 1 << 20  # about 26 KB in the largest of 106 real battles: a damaged offset can't load a whole recording
KINDS = {"planes": "air", "tanks": "ground", "ships": "ship", "helicopters": "heli"}  # gamedata/missions/cta/<folder>/
DIFFICULTIES = {0: "ab", 5: "rb", 10: "sb"}  # shortcut: only 5 was seen in real files (game 2.59), check 0 and 10 with such replays
STATUS = {"success": "win", "fail": "loss"}  # none: the player left before the end
SAME_BATTLE_S = 60  # a replay's last second and a death read from the log a little later
WAIT_S = 2 * 3600  # no replay by then (Autosave Replays off): the name goes


def _text(head: bytes, at: int, size: int) -> str:
    return head[at:at + size].split(b"\0", 1)[0].decode("utf-8", "replace")


def _players(comments: dict) -> tuple:
    """Everybody in a battle, and the author's own line (None if the file doesn't have it)."""
    players = comments["player"] if isinstance(comments["player"], list) else [comments["player"]]  # alone: not a list
    return players, next((p for p in players if str(p.get("userId")) == str(comments["authorUserId"])), None)


def _row(head: bytes, comments: dict, name: str) -> dict | None:
    author = comments["authorUserId"]
    me = _players(comments)[1]
    if me is None:
        return None
    level, mission, cls = _text(head, 8, 128).removeprefix("levels/").removesuffix(".bin"), _text(head, 136, 260), _text(head, 968, 128)
    offline = cls == "singleMission" or "UserMissions" in mission or level == "firing_range"
    folder = re.match(r"gamedata/missions/cta/(\w+)/", mission)
    crafts = comments.get("uiScriptsData", {}).get("playersInfo", {}).get(f"__int_{author}", {}).get("crafts", {})
    made = re.search(r"wtftd_(?:ch-(\w+)-(\w+)-)?([^/\\]+)\.blk$", mission)  # WTFTD's own missions: no players' list, the file's named after the vehicle
    return {
        "file": name, "me": me["name"], "clan": me.get("clanTag", ""), "start": struct.unpack_from("<I", head, 908)[0], "level": level, "offline": offline,
        "title": _text(head, 780, 128) if offline else "",  # a battle's name is its map
        "kind": KINDS.get(folder.group(1), "") if folder else "", "diff": DIFFICULTIES.get(head[688] & 15, ""),
        "result": STATUS.get(comments.get("status"), "left"), "played": int(comments["timePlayed"]),
        "vehicles": list(dict.fromkeys(crafts.values())) or ([made.group(3)] if made else []),
        **({"challenge": made.group(1, 2)} if made and made.group(1) else {}),
        "kills": me.get("kills", me.get("airKills", 0)) + me.get("groundKills", 0) + me.get("navalKills", 0),
        "ai": me.get("aiKills", 0) + me.get("aiGroundKills", 0) + me.get("aiNavalKills", 0),  # AI vehicles: apart from the kills per death
        "deaths": me.get("deaths", 0), "assists": me.get("assists", 0), "score": me.get("score", 0),
        "damage": me.get("awardDamage", 0) + me.get("damageZone", 0),  # the game's two "damage" columns: ships, then zones and bases
    }


def summary(rows: list) -> dict:
    """The overlay's numbers, from the newest row on: real battles only, and the win rate of those with a result."""
    rows = [r for r in rows if not r["offline"]]
    if not rows:
        return {}
    won, lost = (sum(r["result"] == x for r in rows) for x in ("win", "loss"))
    kills, deaths = (sum(r[x] for r in rows) for x in ("kills", "deaths"))
    return {"pilot": rows[0]["me"], "battles": len(rows), "kills": kills, "deaths": deaths, "kd": round(kills / max(deaths, 1), 2),
            **({"winrate": round(won / (won + lost) * 100)} if won + lost else {})}


def _read(path: Path) -> tuple:
    """A replay's header and results, (head, None) without results."""
    with open(path, "rb") as f:
        head = f.read(HEADER)
        at = struct.unpack_from("<I", head, 684)[0]
        if head[:4] != MAGIC or not at:
            return head, None
        f.seek(at + 1)
        return head, vromfs.parse_blk(f.read(RESULTS_MAX), [])


def read_battle(path: Path) -> dict | None:
    """One replay -> its row, None if it can't be read: being written (no results yet), damaged, of an unknown shape."""
    try:
        head, comments = _read(path)
        return _row(head, comments, path.name) if comments else None
    except Exception:  # a file of any shape: it's only counted, the list goes on
        return None


def _teammate(path: Path, name: str) -> dict | None:
    """The line of the player's own team that goes by this name, if there's one."""
    try:
        players, me = _players(_read(path)[1])
        return next((p for p in players if p is not me and p.get("team") == me["team"] and battle.named(name, p["name"])), None)
    except Exception:  # as above: nobody is named on a doubt
        return None


def teamkills(folder: Path, rows: list, killers: list) -> tuple:
    """Those of the battle log's killers who were on the player's team: the log doesn't tell, only the replay's teams do, and
    a replay alone says a teammate killed somebody, not whom. -> (what to keep, those whose replay isn't there yet).
    Enemies, AI vehicles and offline missions leave no trace."""
    filed, waiting = [], []
    for name, at in killers:
        row = next((r for r in rows if r["start"] <= at <= r["start"] + r["played"] + SAME_BATTLE_S), None)
        if not row:
            if time.time() - at < WAIT_S:
                waiting.append((name, at))
            continue
        mate = None if row["offline"] else _teammate(folder / row["file"], name)
        if mate:
            filed.append({"name": mate["name"], "clan": mate.get("clanTag", ""), "at": int(at), "level": row["level"], "file": row["file"]})
    return filed, waiting


def refresh(folder: Path | None, index) -> dict:
    """The index of a Replays folder: the files that changed read again, the ones gone dropped."""
    known = index["files"] if isinstance(index, dict) and index.get("v") == VERSION and isinstance(index.get("files"), dict) else {}
    files = {}
    try:
        with os.scandir(folder or "") as it:
            entries = [(e.name, e.path, e.stat()) for e in it if e.name.lower().endswith(".wrpl") and e.is_file()]
    except OSError:  # no such folder
        entries = []
    for name, path, st in entries:
        old = known.get(name)
        same = old and old["size"] == st.st_size and old["mtime"] == st.st_mtime_ns
        files[name] = old if same else {"size": st.st_size, "mtime": st.st_mtime_ns, "row": read_battle(Path(path))}
    return {"v": VERSION, "files": files}


def listing(index: dict) -> dict:
    """The battles, newest first, and how many files couldn't be read."""
    rows = [x["row"] for x in index["files"].values() if x["row"]]
    return {"rows": sorted(rows, key=lambda r: r["start"], reverse=True), "skipped": len(index["files"]) - len(rows)}
