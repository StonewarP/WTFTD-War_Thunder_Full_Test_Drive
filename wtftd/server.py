"""Local web server: static UI + JSON API + wiki image cache. Binds to 127.0.0.1 only."""
from __future__ import annotations

import json
import mimetypes
import re
import shutil
import socket
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import DONATE, REPO, __version__, builder, cdk, game, maptex, mission, terrain
from .paths import CACHE, DATA, HOME, USER, WEB

ROOT = HOME
IMG_CACHE = CACHE / "img"
MISSION_SETUPS = USER / "missions"
UA = "WTFTD/1.0 (local War Thunder test drive tool)"

IMAGE_SOURCES = {
    "unit": ("https://static.encyclopedia.warthunder.com/images/{}.png", ".png"),
    "flag": ("https://wiki.warthunder.com/static/country_svg/country_{}.svg", ".svg"),
    "ammo": ("https://static.encyclopedia.warthunder.com/gui_skin/{}.png", ".png"),
}
SAFE_ID = re.compile(r"^[A-Za-z0-9_\-.]{1,120}$")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/x-icon", ".ico")


# --------------------------------------------------------------------------- state

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.details: dict | None = None
        self.vehicles: dict | None = None
        self.catalog: dict | None = None
        self.update = {"running": False, "log": [], "error": None, "done": False,
                       "remote": None, "checked": 0, "before": None, "after": None}
        USER.mkdir(exist_ok=True)

    # settings -------------------------------------------------------------
    def settings(self) -> dict:
        s = read_json(USER / "settings.json", {})
        return s if isinstance(s, dict) else {}

    def save_settings(self, s: dict):
        write_json(USER / "settings.json", s)

    def game_dir(self) -> Path | None:
        custom = self.settings().get("gameDir")
        if custom:
            p = Path(custom).expanduser()
            return (game.resolve_game_dir(p) or p) if p.exists() else None
        return game.detect_game_dir()

    def get_details(self) -> dict:
        with self.lock:
            if self.details is None:
                self.details = read_json(DATA / "details.json", {})
            return self.details

    def get_vehicles(self) -> dict:
        with self.lock:
            if self.vehicles is None:
                self.vehicles = {v["id"]: v for v in read_json(DATA / "vehicles.json", [])}
            return self.vehicles

    def get_catalog(self) -> dict:
        with self.lock:
            if self.catalog is None:
                self.catalog = read_json(DATA / "weapons.json", {})
            return self.catalog

    def cdk_enabled(self) -> bool:
        return self.settings().get("cdk", True) is not False

    def host_for(self, cat: str) -> str:
        hosts = self.settings().get("hosts") or {}
        return (hosts.get(cat) if isinstance(hosts, dict) else "") or cdk.DEFAULT_HOSTS.get(cat, "")

    def reload(self):
        with self.lock:
            self.details = None
            self.vehicles = None
            self.catalog = None


STATE = State()


def read_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tmp.replace(path)


# --------------------------------------------------------------------------- images

_img_locks: dict[str, threading.Lock] = {}
_img_locks_guard = threading.Lock()


def cached_image(kind: str, ident: str) -> Path | None:
    _, ext = IMAGE_SOURCES[kind]
    folder = IMG_CACHE / kind
    path = folder / f"{ident}{ext}"
    miss = folder / f"{ident}.missing"
    if path.exists():
        return path
    if miss.exists() and time.time() - miss.stat().st_mtime < 7 * 86400:
        return None
    with _img_locks_guard:
        lock = _img_locks.setdefault(f"{kind}/{ident}", threading.Lock())
    with lock:
        if path.exists():
            return path
        folder.mkdir(parents=True, exist_ok=True)
        for url in image_urls(kind, ident):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=15) as r:
                    body = r.read()
                if len(body) < 64:
                    continue
                tmp = path.with_suffix(".part")
                tmp.write_bytes(body)
                tmp.replace(path)
                return path
            except (urllib.error.URLError, OSError, TimeoutError, ValueError):
                continue
        try:
            miss.write_text("")
        except OSError:
            pass
        return None


def image_urls(kind: str, ident: str) -> list[str]:
    """Wiki image first, then variants and the game's own thumbnails (via the datamine)."""
    url_fmt, _ = IMAGE_SOURCES[kind]
    urls = [url_fmt.format(ident)]
    if kind == "unit":
        low = ident.lower()
        if low.startswith("nt_"):
            urls.append(url_fmt.format(low[3:]))
        tex = "https://raw.githubusercontent.com/gszabi99/War-Thunder-Datamine/master/tex.vromfs.bin_u/{}/{}.png"
        urls += [tex.format(folder, low) for folder in ("aircrafts", "tanks", "ships")]
        if low.startswith("nt_"):
            urls.append(tex.format("aircrafts", low[3:]))
    return urls


# --------------------------------------------------------------------------- app window presence
# macOS keeps the browser running when its last window is closed: the page says "bye" when it goes
# away, and any API call after that (a reload) cancels it. __main__ uses this to quit with the window.
PAGE = {"seen": 0.0, "bye": 0.0}


def page_closed(grace: float = 3.0) -> bool:
    return PAGE["bye"] > PAGE["seen"] and time.time() - PAGE["bye"] > grace


# --------------------------------------------------------------------------- API

def api_status():
    gd = STATE.game_dir()
    meta = read_json(DATA / "meta.json", {})
    um = game.user_missions_dir(gd) if gd else None
    return {
        "platform": sys.platform,
        "gameDir": str(gd) if gd else None,
        "gameFound": bool(gd),
        "steam": bool(gd and game.is_steam_install(gd)),
        "userMissions": str(um) if um else None,
        "levels": sorted(game.installed_levels(gd)),
        "data": meta,
        "dataReady": (DATA / "vehicles.json").exists(),
        "oodle": oodle_dll(gd),
        "settings": STATE.settings(),
        "cdk": {"enabled": STATE.cdk_enabled(), "defaultHosts": cdk.DEFAULT_HOSTS,
                "airMethod": STATE.settings().get("airMethod") or "custom",
                **cdk.status(gd, USER)},
    }


# --------------------------------------------------------------------------- new app version (GitHub releases)
_release = {"checked": 0.0, "latest": None}
RELEASE_CHECK_EVERY = 6 * 3600
APP_ASSET = {"win32": ".exe", "darwin": "-macos.zip"}  # release download of this platform


def _version_tuple(tag: str) -> tuple:
    m = re.match(r"v?(\d+)\.(\d+)(?:\.(\d+))?", tag or "")
    return tuple(int(x or 0) for x in m.groups()) if m else (0, 0, 0)


def app_version() -> dict:
    """This WTFTD's version and the latest published release (checked at most every 6 h)."""
    if time.time() - _release["checked"] > RELEASE_CHECK_EVERY:
        _release["checked"] = time.time()
        try:
            req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases?per_page=10",
                                         headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                releases = [x for x in json.load(r) if isinstance(x, dict) and not x.get("draft")]
            top = max(releases, key=lambda x: _version_tuple(x.get("tag_name", "")), default=None)
            if top:
                ext = APP_ASSET.get(sys.platform, ".exe")
                exe = next((a.get("browser_download_url") for a in top.get("assets", []) if str(a.get("name", "")).lower().endswith(ext)), None)
                _release["latest"] = {"tag": top.get("tag_name"), "name": top.get("name"), "url": top.get("html_url"), "exe": exe,
                                      "notes": (top.get("body") or "")[:2000]}
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            pass  # offline / private repository: no alert
    latest = _release["latest"]
    newer = bool(latest and _version_tuple(latest["tag"]) > _version_tuple(__version__))
    return {"version": __version__, "repo": f"https://github.com/{REPO}", "latest": latest, "newer": newer}


_oodle_memo: dict = {}


def oodle_dll(gd: Path | None) -> str | None:
    """Oodle runtime used to read the game's map textures: the one set in Settings, else auto-detected (once)."""
    custom = STATE.settings().get("oodleDll")
    if custom:
        custom = str(Path(custom).expanduser())
        return custom if Path(custom).is_file() else None
    key = str(gd)
    if key not in _oodle_memo:
        _oodle_memo[key] = maptex.find_oodle(gd)
    return _oodle_memo[key]


def api_vehicle(vid: str):
    d = STATE.get_details().get(vid)
    if d is None:
        return None
    return d


def list_generated():
    gd = STATE.game_dir()
    if not gd:
        return []
    um = game.user_missions_dir(gd)
    out = []
    if um.exists():
        for p in sorted(um.glob("wtftd_*.blk"), key=lambda p: -p.stat().st_mtime):
            out.append({"file": p.name, "mtime": int(p.stat().st_mtime), "size": p.stat().st_size})
    return out


REMOTE_VERSION_URL = "https://raw.githubusercontent.com/gszabi99/War-Thunder-Datamine/master/version"
AUTO_CHECK_EVERY = 3 * 3600  # seconds


def run_update():
    st = STATE.update
    before = read_json(DATA / "meta.json", {})
    st.update(running=True, log=[], error=None, done=False, before=before.get("version"), after=None, progress=0.0)

    class Progress:
        def __call__(self, msg):
            st["log"].append(msg)
            st["log"] = st["log"][-200:]

        def set_frac(self, frac):
            st["progress"] = max(st.get("progress") or 0.0, frac)  # never goes backwards

    progress = Progress()

    try:
        meta = builder.build(pull=True, progress=progress)
        STATE.reload()
        # vehicles added since last build may now have a wiki image: retry the ones marked missing
        for miss in (IMG_CACHE / "unit").glob("*.missing"):
            try:
                miss.unlink()
            except OSError:
                pass
        st["after"] = meta.get("version")
        st["newVehicles"] = max(0, int(meta.get("vehicles", 0)) - int(before.get("vehicles", 0) or 0))
        st["done"] = True
    except Exception as e:  # report any builder failure to the UI
        st["error"] = str(e)
    finally:
        st["running"] = False


def remote_version() -> str | None:
    try:
        req = urllib.request.Request(REMOTE_VERSION_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            v = r.read(64).decode("utf-8", "ignore").strip()
        return v if re.fullmatch(r"[0-9.]+", v) else None
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None


def check_for_update(start: bool = True) -> dict:
    """Compares the published datamine version with ours; rebuilds in the background when newer."""
    st = STATE.update
    remote = remote_version()
    st["remote"], st["checked"] = remote, int(time.time())
    meta = read_json(DATA / "meta.json", {})
    local = meta.get("version")
    # newer game patch, or data built by an older WTFTD that lacks fields this version needs
    st["available"] = bool(remote and remote != local) or (bool(meta) and meta.get("schema", 1) < builder.SCHEMA)
    if start and st["available"] and not st["running"]:
        threading.Thread(target=run_update, daemon=True).start()
    return st


def auto_update_loop():
    time.sleep(4)
    while True:
        if STATE.settings().get("autoUpdate", True) is not False and not STATE.update["running"]:
            check_for_update(start=True)
        time.sleep(AUTO_CHECK_EVERY)


# --------------------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "WTFTD"

    def log_message(self, fmt, *args):  # quiet
        pass

    # helpers --------------------------------------------------------------
    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, cache=False):
        try:
            body = path.read_bytes()
        except OSError:
            return self.send_error(HTTPStatus.NOT_FOUND)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/json", "text/javascript"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=2592000, immutable" if cache else "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 2_000_000:
            raise ValueError("Body too large")
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def local_origin(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        origin = self.headers.get("Origin")
        if host not in ("127.0.0.1", "localhost"):
            return False
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
            return False
        return True

    # GET ------------------------------------------------------------------
    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith("/api/"):
            # reads expose settings, setups and paths: only for this app's own page (blocks DNS rebinding)
            if not self.local_origin():
                return self.send_json({"error": "forbidden"}, 403)
            PAGE["seen"] = time.time()
            return self.get_api(path[5:])
        if path.startswith("/img/levelmap/"):
            meta = captured_map(path.rsplit("/", 1)[-1])
            if meta:
                return self.send_file(MAPS / meta["file"])
            return self.send_error(HTTPStatus.NOT_FOUND)
        if path.startswith("/img/terrain/"):
            level = path.rsplit("/", 1)[-1].removesuffix(".bin")
            if re.fullmatch(r"[a-z0-9_]+", level) and terrain.grid_path(level).exists():
                return self.send_file(terrain.grid_path(level), cache=True)
            return self.send_error(HTTPStatus.NOT_FOUND)
        if path.startswith("/img/maptex/"):
            name = path.rsplit("/", 1)[-1].removesuffix(".png")
            try:
                gd = STATE.game_dir()
                return self.send_file(maptex.png_path(gd, name, oodle_dll(gd)), cache=True)
            except (maptex.MapTexError, OSError) as e:
                return self.send_json({"error": str(e)}, 404)
        if path.startswith("/img/"):
            parts = path.split("/")
            if len(parts) == 4 and parts[2] in IMAGE_SOURCES:
                ident = parts[3].rsplit(".", 1)[0]
                if SAFE_ID.match(ident):
                    p = cached_image(parts[2], ident)
                    if p:
                        return self.send_file(p, cache=True)
            self.send_response(404)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return
        if path.startswith("/data/"):
            rel = path[6:]
            target = (DATA / rel).resolve()
            if DATA.resolve() in target.parents and target.suffix == ".json" and "scenarios" not in target.parts:
                return self.send_file(target)
            return self.send_error(HTTPStatus.NOT_FOUND)
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (WEB / rel).resolve()
        if WEB.resolve() not in target.parents or not target.is_file():
            return self.send_error(HTTPStatus.NOT_FOUND)
        return self.send_file(target)

    def get_api(self, route: str):
        if route == "status":
            return self.send_json(api_status())
        if route.startswith("vehicle/"):
            vid = route.split("/", 1)[1]
            d = api_vehicle(vid) if SAFE_ID.match(vid) else None
            return self.send_json(d) if d is not None else self.send_json({"error": "not found"}, 404)
        if route == "setups":
            return self.send_json(read_json(USER / "setups.json", []))
        if route == "missions":
            return self.send_json(list_generated())
        if route.startswith("terrain/"):
            level = route.split("/", 1)[1]
            gd = STATE.game_dir()
            try:
                meta = terrain.terrain(gd, level, oodle_dll(gd))
            except (terrain.TerrainError, OSError, struct.error) as e:
                return self.send_json({"available": False, "reason": str(e)})
            if not meta:
                return self.send_json({"available": False, "reason": "no heightmap"})
            return self.send_json({**meta, "available": True,
                                   "url": f"/img/terrain/{level}.bin?v={int(terrain.grid_path(level).stat().st_mtime)}"})
        if route == "app-version":
            return self.send_json(app_version())
        if route.startswith("level-map/"):
            meta = level_map(route.split("/", 1)[1])
            return self.send_json(meta) if meta else self.send_json({"error": "no map"}, 404)
        if route.startswith("scenario-units/"):
            try:
                return self.send_json(mission.scenario_units(route.split("/", 1)[1]))
            except mission.MissionError as e:
                return self.send_json({"error": str(e)}, 404)
        if route.startswith("mission-setup/"):
            f = route.split("/", 1)[1]
            if not re.fullmatch(r"wtftd_[A-Za-z0-9_\-]+", f):
                return self.send_json({"error": "bad name"}, 400)
            return self.send_json(read_json(MISSION_SETUPS / f"{f}.json", None))
        if route == "update":
            return self.send_json(STATE.update)
        return self.send_json({"error": "unknown route"}, 404)

    # POST -----------------------------------------------------------------
    def do_POST(self):
        if not self.local_origin():
            return self.send_json({"error": "forbidden"}, 403)
        route = urlparse(self.path).path[5:] if self.path.startswith("/api/") else ""
        if route == "bye":  # the app page is closing (navigator.sendBeacon)
            PAGE["bye"] = time.time()
            return self.send_json({"ok": True})
        PAGE["seen"] = time.time()
        try:
            body = self.read_body()
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)
        try:
            return self.post_api(route, body)
        except mission.MissionError as e:
            return self.send_json({"error": str(e)}, 400)
        except OSError as e:
            return self.send_json({"error": f"File error: {e}"}, 500)

    def post_api(self, route: str, body: dict):
        if route == "generate":
            gd = STATE.game_dir()
            if not gd:
                return self.send_json({"error": "War Thunder folder not found. Set it in Settings."}, 400)
            setup = dict(body)
            body, files = self.prepare_cdk(body)
            name, text = mission.build(body)
            if files:
                cdk.write_files(gd, USER, files, body.get("_pkg", "pkg_local"))
            # keep the exact setup next to the mission so "Load" can restore it
            write_json(MISSION_SETUPS / (name[:-4] + ".json"), setup)
            try:
                su = mission.scenario_units(str(body.get("scenario", "")))
                me = next((u for u in su["units"] if u.get("player")), None)
                pl = (body.get("edits") or {}).get("player") or {}
                if me:
                    set_capture_hint(su["level"], float(pl.get("x", me["x"])), float(pl.get("z", me["z"])))
            except (mission.MissionError, ValueError, TypeError):
                pass
            um = game.user_missions_dir(gd)
            um.mkdir(exist_ok=True)
            out = um / name
            out.write_text(text, encoding="utf-8")
            return self.send_json({"ok": True, "file": name, "path": str(out), "cdkFiles": sorted(files),
                                   "host": body.get("unitClass", "")})
        if route == "target-swaps":  # vehicles "Training targets" puts in place of the scenario's enemies
            try:
                scen = mission.load_scenario(str(body.get("scenario", "")))
                wing = ((scen.get("mission_settings") or {}).get("player") or {}).get("wing")
                return self.send_json(mission.retarget_map(scen.get("units") or {}, wing, _target_pool(body)))
            except mission.MissionError as e:
                return self.send_json({"error": str(e)}, 400)
        if route == "preview":
            body, files = self.prepare_cdk(body)
            name, text = mission.build(body)
            pkg = body.get("_pkg", "pkg_local")
            return self.send_json({"file": name, "text": text, "files": {f"{pkg}/{k}": v for k, v in files.items()}})
        if route == "cdk-cleanup":
            gd = STATE.game_dir()
            removed = cdk.cleanup(gd, USER) if gd else 0
            return self.send_json({"removed": removed, **api_status()})
        if route == "launch":
            how = game.launch(STATE.game_dir())
            return self.send_json({"ok": True, "via": how})
        if route == "open-url":  # release page / issue forms / donation page of this project only
            url = str(body.get("url", ""))
            if url.startswith(f"https://github.com/{REPO}/") or url == DONATE:
                import webbrowser
                webbrowser.open(url)
                return self.send_json({"ok": True})
            return self.send_json({"error": "forbidden"}, 403)
        if route == "open-folder":
            gd = STATE.game_dir()
            if gd:
                um = game.user_missions_dir(gd)
                um.mkdir(exist_ok=True)
                game.open_folder(um)
            return self.send_json({"ok": bool(gd)})
        if route == "settings":
            s = STATE.settings()
            for k in ("gameDir", "lang", "missionType", "theme", "cdk", "hosts", "airMethod", "autoUpdate", "oodleDll"):
                if k in body:
                    s[k] = body[k]
            if s.get("gameDir") and not game.resolve_game_dir(Path(s["gameDir"]).expanduser()):
                return self.send_json({"error": "This folder does not look like a War Thunder install."}, 400)
            if s.get("oodleDll") and maptex.oodle_version(Path(s["oodleDll"]).name) is None:
                return self.send_json({"error": "Pick an Oodle runtime file: oo2core_<version>_win64.dll (Windows) or liboo2core*.dylib (macOS)."}, 400)
            STATE.save_settings(s)
            return self.send_json(api_status())
        if route == "setups":
            if not isinstance(body.get("setups"), list):
                return self.send_json({"error": "setups must be a list"}, 400)
            write_json(USER / "setups.json", body["setups"][:500])
            return self.send_json({"ok": True})
        if route == "delete-mission":
            gd = STATE.game_dir()
            f = str(body.get("file", ""))
            if gd and re.fullmatch(r"wtftd_[A-Za-z0-9_\-]+\.blk", f):
                p = game.user_missions_dir(gd) / f
                if p.exists():
                    p.unlink()
                (MISSION_SETUPS / (f[:-4] + ".json")).unlink(missing_ok=True)
            return self.send_json(list_generated())
        if route == "update-check":
            return self.send_json(check_for_update(start=bool(body.get("start", True))))
        if route == "update":
            if not STATE.update["running"]:
                threading.Thread(target=run_update, daemon=True).start()
            return self.send_json(STATE.update)
        return self.send_json({"error": "unknown route"}, 404)


TARGET_CLASSES = {"ground": ("tank", "tank_destroyer"), "air": ("fighter", "assault", "bomber"),
                  "ship": ("destroyer", "cruiser"), "boat": ("torpedo_boat", "gun_boat", "torpedo_gun_boat", "submarine_chaser")}


def _target_pool(body: dict) -> dict:
    """Vehicles used as training targets for the chosen level: {unit block: [ids]}."""
    tg = body.get("targets") or {}
    mode = tg.get("mode")
    if mode not in ("match", "br"):
        return {}
    vehicles = STATE.get_vehicles()
    me = vehicles.get(str(body.get("vehicle", "")))
    try:
        br = float(tg.get("br")) if mode == "br" else float((me or {}).get("br", [None, None])[1] or 0)
    except (TypeError, ValueError):
        br = 0.0
    if not br:
        return {}
    scen = mission.load_scenario(str(body.get("scenario", "")))
    pool = {}
    for block, cats in (("tankModels", ("ground",)), ("armada", ("air",)), ("ships", ("ship", "boat"))):
        enemies = [u for u in mission._as_list((scen.get("units") or {}).get(block))
                   if isinstance(u, dict) and (u.get("props") or {}).get("army") == 2]
        if not enemies:
            continue
        # keep boats vs ships as in the scenario
        orig = {vehicles.get(u.get("unit_class"), {}).get("c") for u in enemies}
        wanted = [c for c in cats if c in orig] or list(cats)
        cands = [v for v in vehicles.values()
                 if v["c"] in wanted and not v.get("h") and v.get("br") and v["br"][1]
                 and v.get("k") in sum((TARGET_CLASSES[c] for c in wanted), ())]
        for width in (0.35, 0.7, 1.4, 3.0):
            near = [v for v in cands if abs(v["br"][1] - br) <= width]
            if len(near) >= min(4, len(enemies)):
                break
        near.sort(key=lambda v: (abs(v["br"][1] - br), v["id"]))
        # mix nations: round-robin over nations
        by_nation: dict[str, list] = {}
        for v in near:
            by_nation.setdefault(v["n"], []).append(v["id"])
        mixed = []
        while any(by_nation.values()):
            for n in sorted(by_nation):
                if by_nation[n]:
                    mixed.append(by_nation[n].pop(0))
        if mixed:
            pool[block] = mixed[:max(len(enemies), 4)]
    return pool


def _prepare_cdk(body: dict) -> tuple[dict, dict]:
    """Custom-vehicle mode: writes nothing, returns (mission cfg, files to write under pkg_local)."""
    body = dict(body, _targetPool=_target_pool(body))
    veh0 = STATE.get_vehicles().get(str(body.get("vehicle", "")))
    if veh0 and veh0.get("n") not in (None, "", "other"):
        crew_units = {f"country_{veh0['n']}": [veh0["id"]]}
        if STATE.cdk_enabled() and veh0["c"] == "ground":
            host0 = STATE.host_for("ground")
            if host0:
                crew_units.setdefault("country_usa" if host0.startswith("us_") else f"country_{veh0['n']}", []).append(host0)
        body["_crewUnits"] = crew_units
    if not STATE.cdk_enabled() or body.get("cdk") is False:
        return body, {}
    vid = str(body.get("vehicle", ""))
    veh = STATE.get_vehicles().get(vid)
    det = STATE.get_details().get(vid)
    if not veh or det is None:
        raise mission.MissionError("Unknown vehicle")
    air_method = STATE.settings().get("airMethod") or "custom"
    if air_method not in cdk.AIR_METHODS:
        air_method = "custom"
    host = STATE.host_for(veh["c"])
    if not host and not (veh["c"] in ("air", "heli") and air_method == "custom"):
        raise mission.MissionError(f"No host vehicle set for {veh['c']}. Pick a vehicle you own in Settings → Custom vehicles.")
    mods = dict(body.get("mods") or {})
    unit_data = None
    if (body.get("cheats") or {}).get("immortal"):
        mods["invulnerable"] = True
    non_std = any(isinstance(v, dict) for v in (body.get("pylons") or {}).values())
    if mods.get("invulnerable") or non_std:
        # needs the local datamine copy (damage model, pylon layout for non-standard weapons)
        unit_data = builder.load(builder.unit_file(vid, veh["c"]))
    try:
        files, preset, unit_class, pkg = cdk.build_files(vid, veh["c"], det, mods, host,
                                                         body.get("pylons"), air_method, unit_data,
                                                         STATE.get_catalog())
    except cdk.CdkError as e:
        raise mission.MissionError(str(e))
    body = dict(body, unitClass=unit_class, _pkg=pkg)
    if preset:
        body["preset"] = preset
    return body, files


Handler.prepare_cdk = staticmethod(_prepare_cdk)


# --------------------------------------------------------------------------- tactical map capture
# While a battle / mission runs, War Thunder serves its tactical map on http://localhost:8111
# (map.img + map_info.json, the API external map tools use). We save it for the level of the
# mission WTFTD generated last, so the scenario editor can draw the real map under the units.

WT_API = "http://127.0.0.1:8111"
MAPS = CACHE / "maps"
_capture = {"key": None, "hint": None}


def _wt_get(path: str, timeout: float = 1.0) -> bytes | None:
    try:
        with urllib.request.urlopen(WT_API + path, timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None


def set_capture_hint(level: str, x: float, z: float):
    _capture["hint"] = {"level": level, "x": x, "z": z}


def _matches(level_info: dict, mn, mx) -> bool:
    for a, b in (("a0", "a1"), ("t0", "t1")):
        if a in level_info and b in level_info:
            if all(abs(level_info[a][i] - mn[i]) < 2 and abs(level_info[b][i] - mx[i]) < 2 for i in (0, 1)):
                return True
    return False


def capture_once():
    raw = _wt_get("/map_info.json")
    if not raw:
        return
    try:
        info = json.loads(raw.decode("utf-8", "ignore"))
    except ValueError:
        return
    if not info.get("valid") or not isinstance(info.get("map_min"), list) or not isinstance(info.get("map_max"), list):
        return
    hint = _capture["hint"]
    if not hint:
        return
    mn, mx = [float(c) for c in info["map_min"]], [float(c) for c in info["map_max"]]
    key = (hint["level"], info.get("map_generation"), tuple(mn), tuple(mx))
    if key == _capture["key"]:
        return
    levels = read_json(DATA / "levels.json", {})
    if not _matches(levels.get(hint["level"], {}), mn, mx):
        return  # another map is loaded (not the mission we generated)
    img = _wt_get(f"/map.img?gen={info.get('map_generation', 0)}", timeout=4)
    if not img or len(img) < 1000:
        return
    ext = ".png" if img[:4] == b"\x89PNG" else ".jpg"
    # orientation: compare the player's marker with their known start position (the player has not moved yet)
    z_up = True
    try:
        objs = json.loads((_wt_get("/map_obj.json") or b"[]").decode("utf-8", "ignore"))
        me = next((o for o in objs if isinstance(o, dict) and o.get("icon") == "Player"), None)
        if me and mx[0] > mn[0] and mx[1] > mn[1]:
            ny = (hint["z"] - mn[1]) / (mx[1] - mn[1])
            z_up = abs(float(me["y"]) - (1 - ny)) <= abs(float(me["y"]) - ny)
    except (ValueError, KeyError, TypeError):
        pass
    MAPS.mkdir(parents=True, exist_ok=True)
    for old in MAPS.glob(hint["level"] + ".*"):
        old.unlink()
    (MAPS / (hint["level"] + ext)).write_bytes(img)
    write_json(MAPS / (hint["level"] + ".json"), {"min": mn, "max": mx, "zUp": z_up, "file": hint["level"] + ext,
                                                  "captured": int(time.time())})
    _capture["key"] = key


def map_capture_loop():
    while True:
        try:
            capture_once()
        except Exception:  # never let the capture thread die
            pass
        time.sleep(4)


def captured_map(level: str) -> dict | None:
    if not re.fullmatch(r"[a-z0-9_]+", level or ""):
        return None
    meta = read_json(MAPS / f"{level}.json", None)
    return meta if isinstance(meta, dict) and (MAPS / meta.get("file", "")).exists() else None


def level_map(level: str) -> dict | None:
    """Background layers of the scenario editor for a level, drawn in order:
    the full tactical map, then the (more detailed) ground battle map on top.
    From the game files when possible, else the map captured while playing."""
    if not re.fullmatch(r"[a-z0-9_]+", level or ""):
        return None
    info = read_json(DATA / "levels.json", {}).get(level) or {}
    gd = STATE.game_dir()
    layers, oodle, no_oodle = [], None, False
    for tex, a, b in (("am", "a0", "a1"), ("tm", "t0", "t1")):
        name = info.get(tex)
        if not name or a not in info or not maptex.available(gd, name):
            continue
        if not (maptex.CACHE / f"{name}.png").exists():
            oodle = oodle or oodle_dll(gd)
            if not oodle:
                no_oodle = True
                continue
        layers.append({"url": f"/img/maptex/{name}.png", "min": info[a], "max": info[b], "zUp": True})
    if layers:
        return {"source": "game", "layers": layers}
    cap = captured_map(level)
    if cap:
        return {"source": "capture", "layers": [{"url": f"/img/levelmap/{level}?v={cap.get('captured', 0)}",
                                                 "min": cap["min"], "max": cap["max"], "zUp": cap.get("zUp", True)}]}
    return {"source": None, "layers": [], "noOodle": no_oodle}


def free_port(preferred: int) -> int:
    for port in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 0


def serve(port: int = 8777) -> tuple[ThreadingHTTPServer, str]:
    port = free_port(port)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=auto_update_loop, daemon=True).start()
    threading.Thread(target=map_capture_loop, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"
