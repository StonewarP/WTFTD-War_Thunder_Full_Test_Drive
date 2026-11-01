"""My hangar: what the player marked as owned, their lineups and research plan, in user/hangar.json. The game doesn't tell the app what
the player owns, so a mark is the player's own and goes with the user part of Uninstall. UI in web/hangar.js.

The file can be edited by hand and the page's requests are input too: both go through clean(). A file nothing can read is kept
aside, a real account's hundreds of marks shouldn't vanish at the next click."""
from __future__ import annotations

import json
import re

from .paths import USER

FILE = USER / "hangar.json"
MAX_IDS = 8000  # more than the game has vehicles
MAX_LINEUPS = 200
MAX_LINEUP_SIZE = 40
MAX_GOALS = 200
MODES = ("ab", "rb", "sb")
SAFE_ID = re.compile(r"[A-Za-z0-9_\-.]{1,120}")


def _ids(value, limit: int) -> list:
    """Vehicle ids, each once, in their order. Whatever isn't one is dropped."""
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(x for x in value if isinstance(x, str) and SAFE_ID.fullmatch(x)))[:limit]


def _lineup(x) -> dict | None:
    if not isinstance(x, dict) or not isinstance(x.get("id"), str) or not SAFE_ID.fullmatch(x["id"]):
        return None
    nation = x.get("nation")
    return {"id": x["id"], "name": str(x.get("name") or "").strip()[:60], "nation": nation if isinstance(nation, str) and SAFE_ID.fullmatch(nation) else "",
            "mode": x["mode"] if x.get("mode") in MODES else "rb", "vehicles": _ids(x.get("vehicles"), MAX_LINEUP_SIZE)}


def clean(raw) -> dict:
    """What a hangar can hold."""
    raw = raw if isinstance(raw, dict) else {}
    lineups = raw.get("lineups") if isinstance(raw.get("lineups"), list) else []
    return {"owned": _ids(raw.get("owned"), MAX_IDS), "ignored": _ids(raw.get("ignored"), MAX_IDS), "goals": _ids(raw.get("goals"), MAX_GOALS),
            "lineups": [x for x in map(_lineup, lineups) if x][:MAX_LINEUPS]}


def load() -> dict:
    """The hangar; damaged: the file nothing could read was just kept aside, the page says so once."""
    try:
        with open(FILE, encoding="utf-8") as f:
            return clean(json.load(f))
    except FileNotFoundError:
        return clean(None)
    except ValueError:  # UnicodeDecodeError is one too
        FILE.replace(FILE.with_suffix(".bad.json"))
        return {**clean(None), "damaged": True}


def save(patch) -> dict:
    """The parts a request carries replace the file's, in one step: a stopped write leaves it as it was."""
    patch = patch if isinstance(patch, dict) else {}
    data = {**clean(load()), **{k: v for k, v in clean(patch).items() if k in patch}}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tmp.replace(FILE)
    return data
