"""The game's chat and battle log (its local API, port 8111), for the Battle tab: only what's new since the page last asked.
Other players write the chat: it's shown as plain text, never as markup."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .builder import clean

TAG = re.compile(r"<[^>]*>")  # the game's colour tags
ANOTHER_LIFE_S = 10  # a death told twice (shot down, then crashed) is one: nobody is back in the air this fast


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


def duel(text: str, words: dict) -> tuple | None:
    """A battle log line's (winner, loser), None when it isn't a kill. The game's verb sits between the two names, in the
    language it's played in (words: see builder.build_battle_words); "shot down by" is tried before "shot down"."""
    for word in words.get("killedBy", []):
        loser, said, winner = text.partition(f" {word} ")
        if said:
            return winner, loser
    for word in words.get("killed", []):
        winner, said, loser = text.partition(f" {word} ")
        if said:
            return winner, loser
    return None


def named(side: str, name: str) -> bool:
    """Is this side of a line the player: "=TAG= Name (vehicle)"?"""
    who = side.split(" (", 1)[0]
    return who == name or who.endswith(" " + name)


class Tally:
    """The player's own kills and deaths in this battle, from the battle log: the game's API has no other count. Only the
    lines naming the player count, and a kill takes a loser with a vehicle in brackets: a player, as in the replays' kills.
    after: the last line read, None until the first look, which is the past."""

    def __init__(self):
        self.after, self.kills, self.deaths, self.died = None, 0, 0, -ANOTHER_LIFE_S

    def add(self, lines: list, name: str | None, words: dict):
        first, self.after = self.after is None, lines[-1]["id"] if lines else self.after or 0
        for x in [] if first or not name else lines:
            text = x["text"]
            if name not in text:
                continue
            fight = duel(text, words)
            if fight and named(fight[0], name):
                self.kills += " (" in fight[1]
            elif (fight and named(fight[1], name)) or (named(text, name) and any(
                    "".join(text.split()).endswith(w) for w in (*words.get("crashed", []), *words.get("lost", [])))):
                self.deaths += x["time"] - self.died >= ANOTHER_LIFE_S
                self.died = x["time"]

    def values(self) -> dict:
        return {"live_kills": self.kills, "live_deaths": self.deaths, "live_kd": round(self.kills / max(self.deaths, 1), 2)}


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
