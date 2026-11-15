"""WT Live (live.warthunder.com) inside WTFTD: its public feed of what WTFTD installs (vehicles, skins, sounds, missions,
sights, hangars), read on the player's click, and a post's file fetched on another click into the Mods staging folder
(mods.receive), as if the player had picked it. No account: the feed and the files are public. Only WT Live's own
servers are asked, and nothing is sent but the feed's filters."""
from __future__ import annotations

import html
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

from . import __version__, mods

FEED = "https://live.warthunder.com/api/feed/get_regular/"
TYPES = {"model": "vehicle", "camouflage": "skin", "sound": "sound", "mission": "mission", "sight": "sight", "location": "hangar"}
SORTS = ("created", "downloads", "rating", "comments")
PAGE_SIZE = 25  # what the feed gives at a time
DL = re.compile(r"https://live\.warthunder\.com/dl/[A-Za-z0-9]{8,64}/")
CDN = re.compile(r"https://cdn-live\.warthunder\.com/uploads/[A-Za-z0-9_\-./%+()]+")
POST = re.compile(r"https://live\.warthunder\.com/post/\d{1,10}/[a-z]{2}/")  # a post's page, opened in the browser on a click
IMAGE = re.compile(r"https://(?:cdn|images)-live\.warthunder\.com/[A-Za-z0-9_\-./%+()]+")
FILE = re.compile(r"[\w\-. ()\[\]+]{1,100}\.zip", re.I)
HEADERS = {"User-Agent": f"WTFTD/{__version__}", "Accept": "application/json"}
TIMEOUT = 30
PROGRESS: dict = {}  # token -> [bytes received, size]: the page shows the download going
_lock = threading.Lock()


class LiveError(Exception):
    """code: what the page says (wl.err.<code>)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _text(desc: str) -> str:
    """A post's description as plain text: its lines kept, its markup and links' code gone."""
    t = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", str(desc or ""))
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return "\n".join(" ".join(line.split()) for line in t.splitlines()).strip()


def _int(x) -> int:
    return x if isinstance(x, int) and not isinstance(x, bool) and x >= 0 else 0


def _post(p: dict) -> dict | None:
    """What the page shows of a post, checked: one of the types WTFTD installs, a .zip on WT Live's servers."""
    f = p.get("file") if isinstance(p.get("file"), dict) else {}
    link, name = str(f.get("link") or ""), str(f.get("name") or "")
    if p.get("type") not in TYPES or not DL.fullmatch(link) or not FILE.fullmatch(name):
        return None
    text = _text(p.get("description"))
    title = next((line for line in text.splitlines() if line.strip()), name[:-4])
    author = p.get("author") if isinstance(p.get("author"), dict) else {}
    images = [str(i.get("src")) for i in p.get("images") or [] if isinstance(i, dict) and IMAGE.fullmatch(str(i.get("src") or ""))]
    lang = str(p.get("language") or "en")
    return {"id": _int(p.get("id")), "type": p["type"], "kind": TYPES[p["type"]], "created": _int(p.get("created")),
            "url": f"https://live.warthunder.com/post/{_int(p.get('id'))}/{lang if re.fullmatch('[a-z]{2}', lang) else 'en'}/",
            "author": str(author.get("nickname") or "")[:60], "likes": _int(p.get("likes")), "downloads": _int(p.get("downloads")),
            "comments": _int(p.get("comments")), "title": title[:100], "text": text[:4000], "images": images[:12],
            "file": {"name": name, "size": _int(f.get("size")), "link": link}}


def feed(content: str, sort: str = "created", page: int = 0, search: str = "") -> dict:
    """A page of the feed: {posts, more}. search: words, made the site's hashtags (#word), as its own search box does."""
    if content not in TYPES or sort not in SORTS or not isinstance(page, int) or not 0 <= page <= 2000:
        raise LiveError("filter")
    tags = " ".join("#" + w.lstrip("#") for w in re.sub(r"[^\w# ]", " ", str(search or ""))[:80].split() if w.lstrip("#"))
    data = urllib.parse.urlencode({"page": page, "content": content, "sort": sort, "user": "", "searchString": tags, "period": ""}).encode()
    req = urllib.request.Request(FEED, data, {**HEADERS, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            got = json.loads(r.read(4 << 20))
    except (urllib.error.URLError, OSError, ValueError):
        raise LiveError("offline") from None
    raw = (got.get("data") or {}).get("list") if isinstance(got, dict) and got.get("status") == "OK" else None
    if not isinstance(raw, list):
        raise LiveError("offline")
    posts = [x for x in (_post(p) for p in raw if isinstance(p, dict)) if x]
    return {"posts": posts, "more": len(raw) >= PAGE_SIZE}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # the one redirect is looked at before it's followed


class _Counted:
    """The download's stream, its bytes counted for the page (PROGRESS)."""

    def __init__(self, stream, token: str, size: int):
        self.stream, self.token = stream, token
        PROGRESS[token] = [0, size]

    def read(self, n: int) -> bytes:
        chunk = self.stream.read(n)
        with _lock:
            PROGRESS[self.token][0] += len(chunk)
        return chunk


def fetch(token: str, link: str, name: str) -> None:
    """A post's file into the Mods staging folder under token, as a picked .zip: from WT Live's download link, which
    sends to its file on WT Live's own CDN (nowhere else), with Mods' limits (mods.receive)."""
    if not DL.fullmatch(str(link or "")) or not FILE.fullmatch(str(name or "")):
        raise LiveError("file")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(urllib.request.Request(link, headers=HEADERS), timeout=TIMEOUT).close()
        raise LiveError("file")  # no redirect: no file
    except urllib.error.HTTPError as e:
        target = e.headers.get("Location") or ""
        e.close()
    except (urllib.error.URLError, OSError):
        raise LiveError("offline") from None
    if not CDN.fullmatch(target):
        raise LiveError("file")
    try:
        with urllib.request.urlopen(urllib.request.Request(target, headers=HEADERS), timeout=TIMEOUT) as r:
            size = int(r.headers.get("Content-Length") or -1)
            mods.receive(token, name, _Counted(r, token, size), size, "auto")
    except (urllib.error.URLError, OSError, ValueError):
        raise LiveError("offline") from None
    finally:
        PROGRESS.pop(token, None)


def progress(token: str) -> dict:
    done, size = PROGRESS.get(str(token), [0, 0])
    return {"done": done, "size": size}
