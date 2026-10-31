"""The game's chat and battle log (its local API, port 8111), for the Battle tab: only what's new since the page last asked.
Other players write the chat: it's shown as plain text, never as markup."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .builder import clean

TAG = re.compile(r"<[^>]*>")  # the game's colour tags


def _lines(items) -> list:
    return [{"id": x.get("id", 0), "time": x.get("time", 0), "text": clean(TAG.sub("", str(x.get("msg", "")))),
             "sender": clean(str(x.get("sender", ""))), "enemy": x.get("enemy") is True, "mode": str(x.get("mode", ""))}
            for x in items if isinstance(x, dict)] if isinstance(items, list) else []


def _json(raw):
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def damage_lines(get, after: int) -> list:
    """What's new in the battle log's lines, for the crash detection."""
    log = _json(get(f"/hudmsg?lastEvt=0&lastDmg={after}"))
    return _lines(log.get("damage")) if isinstance(log, dict) else []


class Archive:
    """The chat and battle log in a text file a day, on demand. Each line once: a page opened again asks from the start."""

    def __init__(self, folder: Path):
        self.folder, self.last = folder, {}

    def add(self, seen: dict):
        if not seen["up"]:  # a game started again numbers everything from 1
            self.last = {}
            return
        out = []
        for kind in ("chat", "events", "damage"):
            fresh = [x for x in seen[kind] if x["id"] > self.last.get(kind, 0)]
            self.last[kind] = max((x["id"] for x in fresh), default=self.last.get(kind, 0))
            out += [(x["time"], f"{x['time'] // 60}:{x['time'] % 60:02d}  {x['sender'] + ': ' if x['sender'] else ''}{x['text']}") for x in fresh]
        if out:
            self.folder.mkdir(parents=True, exist_ok=True)
            with open(self.folder / f"battle-{time.strftime('%Y_%m_%d')}.txt", "a", encoding="utf-8") as f:
                f.writelines(line + "\n" for _, line in sorted(out, key=lambda x: x[0]))


def news(get, chat: int, event: int, damage: int) -> dict:
    """get: bytes of a game API path, None when the game isn't there (up: False, its numbering starts over next time)."""
    said, log = _json(get(f"/gamechat?lastId={chat}")), _json(get(f"/hudmsg?lastEvt={event}&lastDmg={damage}"))
    log = log if isinstance(log, dict) else {}
    return {"up": said is not None, "chat": _lines(said), "events": _lines(log.get("events")), "damage": _lines(log.get("damage"))}
