"""The game's chat and battle log (its local API, port 8111), for the Battle tab: only what's new since the page last asked.
Other players write the chat: it's shown as plain text, never as markup."""
from __future__ import annotations

import json
import re

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


def news(get, chat: int, event: int, damage: int) -> dict:
    """get: bytes of a game API path, None when the game isn't there (up: False, its numbering starts over next time)."""
    said, log = _json(get(f"/gamechat?lastId={chat}")), _json(get(f"/hudmsg?lastEvt={event}&lastDmg={damage}"))
    log = log if isinstance(log, dict) else {}
    return {"up": said is not None, "chat": _lines(said), "events": _lines(log.get("events")), "damage": _lines(log.get("damage"))}
