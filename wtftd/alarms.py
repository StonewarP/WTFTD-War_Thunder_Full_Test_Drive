"""In-flight speed alarms and their overlay (Windows only).

The game's /indicators can answer {"valid": false} even in flight (seen on 2.59, until the game was restarted), so
speeds come from /state. The aircraft comes from what WTFTD generated, else from /indicators' "type", else as a
fallback from its fuel capacity and engines plus the model the game saved in global.blk (read only, and only that key).
Its speed is then compared to the breaking limits of its flight model (st["lim"] in data/details.json, see
builder.flight_limits): in doubt there is no alarm, never a guess.

What is shown and heard is the player's (My overlay tab, settings.json "overlay", see clean): the window's look, each
line's text ("IAS {ias} / {vne} km/h", see FIELDS) and when it shows, the alarms' thresholds and sounds.

The overlay is a separate click-through window above the game: nothing is injected, nothing touches the game.
"""
from __future__ import annotations

import gc
import json
import re
import sys
import threading
import time
from pathlib import Path

from . import sights
from .paths import WEB

ALARMS = {"airframe": (93, 1400), "gear": (90, 1000), "flaps": (90, 700)}  # default: % of the limit, beep in Hz
POLL_S = 0.1
IDLE_S = 1.0  # not flying: nothing to read fast
REPEAT_MS = 300
BEEP_MS = 150
UNKNOWN_BEEP = (300, 500)
SAVED_MODEL = re.compile(r'selectedAir\s*\{\s*current_model:t="([^"]+)"')

# what an overlay line can show: {name} -> field of /state or /indicators, decimals; "{mach:3}" sets the decimals.
# Any other field the game sends works under its own name: "{RPM 2}", "{bank}"
FIELDS = {"ias": ("IAS, km/h", 0), "tas": ("TAS, km/h", 0), "mach": ("M", 2), "alt": ("H, m", 0), "vy": ("Vy, m/s", 1),
          "aoa": ("AoA, deg", 1), "aos": ("AoS, deg", 1), "g": ("Ny", 1), "g_max": ("g_meter_max", 1),
          "roll": ("Wx, deg/s", 0), "heading": ("compass", 0), "fuel": ("Mfuel, kg", 0), "fuel_max": ("Mfuel0, kg", 0),
          "throttle": ("throttle 1, %", 0), "rpm": ("RPM 1", 0), "thrust": ("thrust 1, kgs", 0),
          "power": ("power 1, hp", 0), "oil": ("oil temp 1, C", 0), "gear": ("gear, %", 0), "flaps": ("flaps, %", 0),
          "airbrake": ("airbrake, %", 0)}
COMPUTED = {"vne": 0, "mne": 2, "gear_max": 0, "flaps_max": 0, "margin": 0, "airframe_pct": 0, "gear_pct": 0,
            "flaps_pct": 0, "fuel_pct": 0}  # see computed(): name -> decimals
FIELD = re.compile(r"\{([^{}:]+)(?::(\d))?\}")
NO_VALUE = "N/A"  # what the game doesn't send, what the aircraft doesn't have

WHEN = {"always": None, "alarm": None, "gear": "gear, %", "flaps": "flaps, %", "airbrake": "airbrake, %"}  # shown if out
MAX_LINES = 30
MAX_TEXT = 120
COLOR = re.compile(r"#[0-9a-fA-F]{6}")
FONT = re.compile(r"[\w .+-]{1,64}")

# fills the preview when the game isn't flying: every line shows, with an alarm on
SAMPLE_LIM = {"v": 1540, "m": 2.1, "gear": 700, "flaps": [[0.2, 1018], [1, 600]], "fuel": [9400], "eng": 2}
SAMPLE_STATE = {"IAS, km/h": 640, "TAS, km/h": 790, "M": 0.75, "H, m": 3200, "Vy, m/s": 12.5, "AoA, deg": 4.2,
                "AoS, deg": 0.1, "Ny": 3.1, "Wx, deg/s": 20, "Mfuel, kg": 6200, "Mfuel0, kg": 9400, "throttle 1, %": 100,
                "RPM 1": 13300, "thrust 1, kgs": 12500, "power 1, hp": 0, "oil temp 1, C": 79, "gear, %": 100,
                "flaps, %": 33, "airbrake, %": 20}

GAME_WINDOW_CLASS = "DagorWClass"
OVERLAY_KEY = "#010101"  # the colour made see-through


def available() -> bool:
    return sys.platform == "win32"


def screen() -> tuple:
    """Screen size in real pixels, whatever this process' DPI awareness (not Windows: a 4K screen, only for sizes)."""
    try:
        import ctypes
        dc = ctypes.windll.user32.GetDC(0)
        size = ctypes.windll.gdi32.GetDeviceCaps(dc, 118), ctypes.windll.gdi32.GetDeviceCaps(dc, 117)  # DESKTOPHORZRES, VERTRES
        ctypes.windll.user32.ReleaseDC(0, dc)
        return size
    except (AttributeError, OSError):
        return 3840, 2160


def labels(lang: str) -> dict:
    """The overlay's words (keys overlay.*) from the UI translations, English when missing."""
    out = {}
    for code in ("en", lang):
        try:
            words = json.loads((WEB / "locales" / f"{code}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        out.update({k.split(".", 1)[1]: v for k, v in words.items() if k.startswith("overlay.")})
    return out


def defaults(words: dict) -> dict:
    """The overlay until the player changes it: lined up with the game's HUD (x, y, size: 4K screen at 150 %)."""
    scale = screen()[1] / 2160
    width = max(len(w) for w in ("IAS", "MACH", words["gear"], words["flaps"])) + 2

    def line(label, text, when="always", alarm=""):
        return {"text": f"{label:<{width}}{text}", "when": when, "alarm": alarm, "color": "", "size": 0}

    return {"x": round(700 * scale), "y": round(55 * scale), "font": "Consolas", "size": round(40 * scale), "bold": False,
            "color": "#E6E6E6", "alert": "#FF0000", "opacity": 100, "show": True, "hotkey": [], "hotkeyName": "",
            "repeat": REPEAT_MS, "alarms": {n: {"on": True, "at": at, "hz": hz, "ms": BEEP_MS} for n, (at, hz) in ALARMS.items()},
            "lines": [line("IAS", "{ias} / {vne} km/h {swept}", alarm="airframe"), line("MACH", "{mach} / {mne}", alarm="airframe"),
                      line(words["gear"], "{ias} / {gear_max} km/h", "gear", "gear"),
                      line(words["flaps"], "{ias} / {flaps_max} km/h", "flaps", "flaps")]}


def _num(v, default, lo, hi):
    return min(hi, max(lo, int(v))) if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def _color(v, default):
    return v if isinstance(v, str) and COLOR.fullmatch(v) else default


def _flag(v, default):
    return v if isinstance(v, bool) else default


def _line(line: dict) -> dict:
    return {"text": str(line.get("text", ""))[:MAX_TEXT], "when": line.get("when") if line.get("when") in WHEN else "always",
            "alarm": line.get("alarm") if line.get("alarm") in ALARMS else "", "color": _color(line.get("color"), ""),
            "size": _num(line.get("size"), 0, 0, 400)}


def clean(cfg, words: dict) -> dict:
    """A complete overlay configuration from what was saved or sent by the page: what's missing or odd gets the default."""
    base = defaults(words)
    if not isinstance(cfg, dict):
        return base
    alarms = cfg.get("alarms") if isinstance(cfg.get("alarms"), dict) else {}
    out = {"x": _num(cfg.get("x"), base["x"], -20000, 20000), "y": _num(cfg.get("y"), base["y"], -20000, 20000),
           "font": cfg["font"] if isinstance(cfg.get("font"), str) and FONT.fullmatch(cfg["font"]) else base["font"],
           "size": _num(cfg.get("size"), base["size"], 6, 400), "bold": _flag(cfg.get("bold"), base["bold"]),
           "color": _color(cfg.get("color"), base["color"]), "alert": _color(cfg.get("alert"), base["alert"]),
           "opacity": _num(cfg.get("opacity"), base["opacity"], 10, 100), "show": _flag(cfg.get("show"), base["show"]),
           "repeat": _num(cfg.get("repeat"), base["repeat"], 100, 10000), "hotkey": [], "hotkeyName": "", "alarms": {}}
    keys = cfg.get("hotkey")
    if isinstance(keys, list) and 0 < len(keys) < 5 and all(type(k) is int and 0 < k < 255 for k in keys):
        out["hotkey"], out["hotkeyName"] = keys, str(cfg.get("hotkeyName", ""))[:32]
    for name, std in base["alarms"].items():
        a = alarms.get(name) if isinstance(alarms.get(name), dict) else {}
        out["alarms"][name] = {"on": _flag(a.get("on"), std["on"]), "at": _num(a.get("at"), std["at"], 1, 200),
                               "hz": _num(a.get("hz"), std["hz"], 37, 32767), "ms": _num(a.get("ms"), std["ms"], 10, 2000)}
    lines = cfg.get("lines")
    out["lines"] = [_line(x) for x in lines if isinstance(x, dict)][:MAX_LINES] if isinstance(lines, list) else base["lines"]
    return out


def flaps_limit(points: list, position: float) -> float:
    """Speed limit at a flap position (0..1): linear between the flight model's points, flat outside them."""
    if position <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if position <= x1:
            return y0 + (y1 - y0) * (position - x0) / (x1 - x0)
    return points[-1][1]


def percents(lim: dict, state: dict) -> dict:
    """{alarm: % of its limit}: the airframe always, gear and flaps only when they are out."""
    ias = state.get("IAS, km/h") or 0
    out = {"airframe": max(ias / lim["v"], (state.get("M") or 0) / lim["m"] if lim["m"] else 0) * 100}
    if (state.get("gear, %") or 0) > 0 and lim.get("gear"):
        out["gear"] = ias / lim["gear"] * 100
    flaps = state.get("flaps, %") or 0
    if flaps > 0 and lim.get("flaps"):
        out["flaps"] = ias / flaps_limit(lim["flaps"], flaps / 100) * 100
    return out


def active(values: dict, alarms: dict) -> list:
    return [name for name, value in values.items() if alarms[name]["on"] and value >= alarms[name]["at"]]


def computed(lim: dict | None, state: dict, words: dict) -> dict:
    """The values that come from the limits: unknown aircraft, none of them. margin: km/h left to the nearest airframe limit."""
    out = {"swept": words["swept"] if lim and "sw" in lim else ""}
    if state.get("Mfuel0, kg"):
        out["fuel_pct"] = (state.get("Mfuel, kg") or 0) / state["Mfuel0, kg"] * 100
    if not lim:
        return out
    ias, mach = state.get("IAS, km/h") or 0, state.get("M") or 0
    out.update({f"{name}_pct": value for name, value in percents(lim, state).items()})
    out.update(vne=lim["v"], mne=lim["m"] or None, gear_max=lim.get("gear") or None,
               margin=min(lim["v"] - ias, ias * (lim["m"] / mach - 1) if lim["m"] and mach else lim["v"]))
    if lim.get("flaps"):
        out["flaps_max"] = flaps_limit(lim["flaps"], (state.get("flaps, %") or 0) / 100)
    return out


def fill(text: str, values: dict) -> str:
    """A line's text with its {values}: what isn't there says N/A."""
    def one(m):
        name, places = m[1].strip(), m[2]
        source, default = FIELDS.get(name, (name, COMPUTED.get(name)))
        v = values.get(source)
        if isinstance(v, str):
            return v
        if v is None or isinstance(v, bool):
            return NO_VALUE
        return f"{v:.{int(places)}f}" if places else f"{v:.{default}f}" if default is not None else f"{v:g}"
    return FIELD.sub(one, text).rstrip()


def shown(line: dict, state: dict, on: list) -> bool:
    if line["when"] == "alarm":
        return bool(on)
    return line["when"] == "always" or (state.get(WHEN[line["when"]]) or 0) > 0


def lines_for(cfg: dict, state: dict, indicators: dict, lim: dict | None, on: list, words: dict) -> list:
    """[(text, colour, size), ...] of the overlay: a line goes to the alert colour with the alarm it follows."""
    values = {**indicators, **state, **computed(lim, state, words)}
    return [(fill(line["text"], values), cfg["alert"] if line["alarm"] in on else line["color"] or cfg["color"],
             line["size"] or cfg["size"]) for line in cfg["lines"] if shown(line, state, on)]


def answer(raw: bytes | None) -> dict:
    """A game API answer, {} when there is none or it says it isn't valid: a bad answer is no reason to stop."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) and data.get("valid") else {}


def flying(raw: bytes | None) -> dict | None:
    """/state while in the air, else None: in the hangar it is valid with zeros."""
    state = answer(raw)
    return state if "Mfuel0, kg" in state and state.get("IAS, km/h") else None


def reported_type(indicators: dict) -> str | None:
    """The vehicle id the game itself names in /indicators."""
    kind = indicators.get("type")
    return kind if isinstance(kind, str) else None


def matches(lim: dict, state: dict, fuel: float | None = None) -> bool:
    """Do this aircraft's fuel capacity (one of its two values, or the mission's own) and engines fit /state?"""
    capacity = state["Mfuel0, kg"]
    return (lim.get("eng") == sum(k.startswith("throttle ") for k in state)
            and any(abs(x - capacity) < 1 for x in lim.get("fuel", []) + ([fuel] if fuel else [])))


def speeds(lim: dict) -> tuple:
    return lim["v"], lim["m"], lim.get("gear"), str(lim.get("flaps"))


def recognise(planes: dict, state: dict, model: str | None) -> dict | None:
    """The limits of the aircraft flown: the one the game saved if it fits /state, else what every aircraft that fits
    shares; None when they differ (or none fits): the choice would change the limits, so nothing is assumed."""
    found = [vid for vid, lim in planes.items() if matches(lim, state)]
    if model in found:
        return planes[model]
    return planes[found[0]] if len({speeds(planes[v]) for v in found}) == 1 else None


def read_model(path: Path) -> str | None:
    try:
        m = SAVED_MODEL.search(path.read_text(encoding="latin-1"))
    except OSError:
        return None
    return m[1] if m else None


def save_file() -> Path | None:
    for root in sights._saves_roots():
        path = root / "last" / "production" / "global.blk"
        if path.is_file():
            return path
    return None


def beep(freq: int, ms: int):
    import winsound  # Windows only: see available()
    winsound.Beep(freq, ms)


class Watch:
    """Reads /state and keeps .display, what the overlay shows: [(text, colour, size), ...].

    get: bytes of a game API path; details: () -> data/details.json; mission_on_map: () -> is the map of the mission
    generated last the one loaded in the game?; save: () -> path of global.blk."""

    def __init__(self, get, details, mission_on_map=lambda: False, save=save_file, lang="en"):
        self.get, self.details, self.mission_on_map, self.save = get, details, mission_on_map, save
        self.words = labels(lang)
        self.cfg = clean(None, self.words)
        self.enabled = False
        self.preview = False  # My overlay's "show it on my screen": without the game, with sample values
        self.hidden = False  # the show / hide key
        self.mission = None  # {"id", "fuel", "unbreakable"}: set when a mission is generated
        self.display = []
        self.stopping = threading.Event()
        self.overlay = None
        self._details, self._planes = None, {}
        self._saved = (None, None)
        self._key, self._lim, self._unbreakable = None, None, False
        self._last_beep = 0.0

    def start_overlay(self):
        if not self.overlay:
            self.overlay = threading.Thread(target=run_overlay, args=(self,), daemon=True)
            self.overlay.start()

    def set_enabled(self, on: bool):
        self.enabled = on
        if on:
            self.start_overlay()

    def set_preview(self, on: bool):
        self.preview = on
        if on:
            self.start_overlay()
        self.display = self.sample() if on else []

    def set_config(self, cfg: dict):
        self.cfg = cfg
        if self.preview:
            self.display = self.sample()

    def sample(self) -> list:
        return lines_for(self.cfg, SAMPLE_STATE, {}, SAMPLE_LIM, active(percents(SAMPLE_LIM, SAMPLE_STATE), self.cfg["alarms"]),
                         self.words)

    def planes(self) -> dict:
        details = self.details()
        if details is not self._details:  # new data after an update
            self._details = details
            self._planes = {vid: d["st"]["lim"] for vid, d in details.items() if (d.get("st") or {}).get("lim")}
        return self._planes

    def model(self) -> str | None:
        """The aircraft the game saved, read again only when the file changes."""
        path = self.save()
        try:
            modified = path.stat().st_mtime
        except (OSError, AttributeError):
            return None
        if modified != self._saved[0]:
            self._saved = (modified, read_model(path))
        return self._saved[1]

    def aircraft(self, state: dict, reported: str | None):
        """Works out the aircraft when what it depends on changes. Beeps once if it is unknown."""
        model, planes = self.model(), self.planes()
        key = (state["Mfuel0, kg"], sum(k.startswith("throttle ") for k in state), model, reported, id(self.mission))
        if key == self._key:
            return
        self._key = key
        m, lim = self.mission, None
        if m and m["id"] in planes and matches(planes[m["id"]], state, m.get("fuel")) and self.mission_on_map():
            lim = planes[m["id"]]  # what WTFTD generated first: custom vehicles keep the name of no real aircraft
        self._unbreakable = bool(lim and m.get("unbreakable"))
        self._lim = lim or planes.get(reported) or recognise(planes, state, model)
        print(f"Alarms: Mfuel0={key[0]}, reported={reported}, saved model={model}, limits={self._lim}", flush=True)
        if not self._lim:
            beep(*UNKNOWN_BEEP)

    def tick(self) -> float:
        """One reading of /state; returns the time until the next one."""
        state = flying(self.get("/state")) if self.enabled else None
        if state is None:
            self.display = self.sample() if self.preview else []
            self._key = None  # the next spawn may be another aircraft, or the same one elsewhere
            return IDLE_S
        cfg = self.cfg
        indicators = answer(self.get("/indicators"))  # every time: it may only start answering mid-flight
        self.aircraft(state, reported_type(indicators))
        lim = self._lim
        on = active(percents(lim, state), cfg["alarms"]) if lim and not self._unbreakable else []
        status = [(self.words["unknown"], cfg["alert"], cfg["size"])] if not lim else \
            [(self.words["unbreakable"], cfg["color"], cfg["size"])] if self._unbreakable else []
        self.display = status + lines_for(cfg, state, indicators, lim, on, self.words)
        if on and time.monotonic() - self._last_beep >= cfg["repeat"] / 1000:
            self._last_beep = time.monotonic()
            for name in on:
                beep(cfg["alarms"][name]["hz"], cfg["alarms"][name]["ms"])
        return POLL_S

    def run(self):
        while True:
            try:
                wait = self.tick()
            except Exception:  # never let the alarms thread die
                wait = IDLE_S
            time.sleep(wait)

    def stop(self):
        self.stopping.set()
        if self.overlay:
            self.overlay.join(1)


def run_overlay(watch: Watch):
    """The overlay window. Runs in its own thread, with every Tk call: the main one waits for the app window."""
    try:
        import ctypes
        import tkinter as tk
        user32 = ctypes.windll.user32
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # real pixels
        previous = user32.GetForegroundWindow()
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", OVERLAY_KEY)
        root.configure(bg=OVERLAY_KEY)
        root.update()
        hwnd = user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT
        WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT, GWL_EXSTYLE = 0x08000000, 0x80, 0x20, -20
        SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                              | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT)  # clicks go through it
        user32.ShowWindow(hwnd, SW_HIDE)
        user32.SetForegroundWindow(previous)  # creating the window took the focus
        rows, drawn = [], None

        def game_focused() -> bool:
            name = ctypes.create_unicode_buffer(32)
            user32.GetClassNameW(user32.GetForegroundWindow(), name, len(name))
            return name.value == GAME_WINDOW_CLASS

        def draw(cfg: dict, lines: list):
            root.geometry(f"+{cfg['x']}+{cfg['y']}")
            root.attributes("-alpha", cfg["opacity"] / 100)
            for i, (text, color, size) in enumerate(lines):
                if i == len(rows):
                    rows.append(tk.Label(root, bg=OVERLAY_KEY, justify="left", bd=0, padx=0, pady=0))
                rows[i].config(text=text, fg=color, font=(cfg["font"], -size, "bold" if cfg["bold"] else "normal"))
                rows[i].pack(anchor="w")
            for row in rows[len(lines):]:
                row.pack_forget()

        def refresh():
            nonlocal drawn
            if watch.stopping.is_set():
                root.destroy()
                return
            cfg, lines = watch.cfg, watch.display
            if (cfg, lines) != drawn:
                drawn = cfg, lines
                draw(cfg, lines)
            keys = cfg["hotkey"]
            if keys and user32.GetAsyncKeyState(keys[-1]) & 1 and game_focused() \
                    and all(user32.GetAsyncKeyState(k) & 0x8000 for k in keys[:-1]):
                watch.hidden = not watch.hidden
            on_game = cfg["show"] and not watch.hidden and game_focused()
            # ShowWindow rather than Tk: Tk would take the focus
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE if lines and (watch.preview or on_game) else SW_HIDE)
            root.after(int(POLL_S * 1000), refresh)

        refresh()
        root.mainloop()
        root = rows = draw = refresh = None
        gc.collect()  # Tk must be freed here: left to Python's exit, in the main thread, it aborts the process
    except Exception as e:  # no Tk in this Python, no display...: the alarms still beep
        print(f"Overlay off: {e}", flush=True)
