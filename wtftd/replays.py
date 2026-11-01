"""My battles: the player's own results, from the replay files the game saves (<game>/Replays/*.wrpl).

Read only, and only two parts of a file: its fixed header and the results at its end, never the recording in between.
The results hold all the players of a battle: only the author's own name and numbers are kept, nobody else's.
Each file is read once: the index (.cache/battles.json) remembers its row by size and date.

What a replay can't tell:
  - the result of a battle left before the end: the game writes it only at the end (no status: "left");
  - which vehicle made which kill, in a battle with several: the numbers are the whole battle's."""
from __future__ import annotations

import os
import re
import struct
from pathlib import Path

from . import vromfs

VERSION = 1  # of the rows in the index: another one reads every file again
MAGIC = b"\xe5\xac\x00\x10"
HEADER = 1096  # the fixed fields end with the battle class
RESULTS_MAX = 1 << 20  # about 26 KB in the largest of 106 real battles: a damaged offset can't load a whole recording
KINDS = {"planes": "air", "tanks": "ground", "ships": "ship", "helicopters": "heli"}  # gamedata/missions/cta/<folder>/
DIFFICULTIES = {0: "ab", 5: "rb", 10: "sb"}  # shortcut: only 5 was seen in real files (game 2.59), check 0 and 10 with such replays
STATUS = {"success": "win", "fail": "loss"}  # none: the player left before the end


def _text(head: bytes, at: int, size: int) -> str:
    return head[at:at + size].split(b"\0", 1)[0].decode("utf-8", "replace")


def _row(head: bytes, comments: dict, name: str) -> dict | None:
    author = comments["authorUserId"]
    players = comments["player"] if isinstance(comments["player"], list) else [comments["player"]]  # alone: not a list
    me = next((p for p in players if str(p.get("userId")) == str(author)), None)
    if me is None:
        return None
    level, mission, cls = _text(head, 8, 128).removeprefix("levels/").removesuffix(".bin"), _text(head, 136, 260), _text(head, 968, 128)
    offline = cls == "singleMission" or "UserMissions" in mission or level == "firing_range"
    folder = re.match(r"gamedata/missions/cta/(\w+)/", mission)
    crafts = comments.get("uiScriptsData", {}).get("playersInfo", {}).get(f"__int_{author}", {}).get("crafts", {})
    made = re.search(r"wtftd_([^/\\]+)\.blk$", mission)  # WTFTD's own missions: no players' list, the file's named after the vehicle
    return {
        "file": name, "me": me["name"], "start": struct.unpack_from("<I", head, 908)[0], "level": level, "offline": offline,
        "title": _text(head, 780, 128) if offline else "",  # a battle's name is its map
        "kind": KINDS.get(folder.group(1), "") if folder else "", "diff": DIFFICULTIES.get(head[688] & 15, ""),
        "result": STATUS.get(comments.get("status"), "left"), "played": int(comments["timePlayed"]),
        "vehicles": list(dict.fromkeys(crafts.values())) or ([made.group(1)] if made else []),
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


def read_battle(path: Path) -> dict | None:
    """One replay -> its row, None if it can't be read: being written (no results yet), damaged, of an unknown shape."""
    try:
        with open(path, "rb") as f:
            head = f.read(HEADER)
            at = struct.unpack_from("<I", head, 684)[0]
            if head[:4] != MAGIC or not at:
                return None
            f.seek(at + 1)
            return _row(head, vromfs.parse_blk(f.read(RESULTS_MAX), []), path.name)
    except Exception:  # a file of any shape: it's only counted, the list goes on
        return None


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
