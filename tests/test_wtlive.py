"""WT Live in Mods: its feed read and checked, a post's file fetched from WT Live's servers only, sight packs into the library."""
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
import zipfile
from email.message import Message
from pathlib import Path
from unittest import mock

from wtftd import mods, sights, wtlive

DL = "https://live.warthunder.com/dl/9c02dfdc84e3281f0091f214575f6a97d16e0594/"
CDN = "https://cdn-live.warthunder.com/uploads/9c/02/df/dc84e3281f0091f214575f6a97d16e0594/ratte_Beckett.zip"


def post(**over):
    p = {"id": 820609, "type": "model", "created": 1540750538, "author": {"nickname": "_Beckett"}, "likes": 855, "downloads": 21600,
         "comments": 297, "description": "<p>Alright, here it is - <b>The Landkreuzer P1000 Ratte</b></p><p>2 engines &amp; skins</p>"
         '<script>alert(1)</script>', "images": [{"src": "https://cdn-live.warthunder.com/uploads/50/0b/ratte-01.jpg"}, {"src": "javascript:alert(1)"}],
         "file": {"name": "ratte_Beckett.zip", "link": DL, "size": 39700942}}
    return {**p, **over}


class Response(io.BytesIO):
    def __init__(self, body: bytes, headers=None):
        super().__init__(body)
        self.headers = Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Feed(unittest.TestCase):
    def test_a_post_as_the_page_shows_it(self):
        p = wtlive._post(post())
        self.assertEqual((p["kind"], p["title"], p["author"], p["file"]["size"]), ("vehicle", "Alright, here it is - The Landkreuzer P1000 Ratte", "_Beckett", 39700942))
        self.assertEqual(p["text"], "Alright, here it is - The Landkreuzer P1000 Ratte\n2 engines & skins\nalert(1)")  # plain text, never markup
        self.assertEqual(p["images"], ["https://cdn-live.warthunder.com/uploads/50/0b/ratte-01.jpg"])
        self.assertEqual(p["url"], "https://live.warthunder.com/post/820609/en/")  # Open on WT Live
        self.assertEqual(wtlive._post(post(language="ru"))["url"], "https://live.warthunder.com/post/820609/ru/")
        for url in (p["url"], "https://live.warthunder.com/post/1/fr/"):
            self.assertTrue(wtlive.POST.fullmatch(url))
        for url in ("https://live.warthunder.com/dl/abc/", "https://evil.example/post/1/en/", "https://live.warthunder.com/post/1/en/x"):
            self.assertFalse(wtlive.POST.fullmatch(url))  # the browser opens a post's page only

    def test_what_wtftd_cant_install_or_doesnt_come_from_wt_live_is_left_out(self):
        for over in ({"type": "video"}, {"type": "image"}, {"file": {"name": "x.zip", "link": "https://evil.example/dl/abcdefgh/"}},
                     {"file": {"name": "x.rar", "link": DL}}, {"file": None}):
            with self.subTest(over):
                self.assertIsNone(wtlive._post(post(**over)))

    def test_the_feed_asked_with_the_sites_own_filters(self):
        sent = {}

        def fake(req, timeout):
            sent.update(urllib.parse.parse_qs(req.data.decode()))
            return Response(json.dumps({"status": "OK", "data": {"list": [post(), post(type="video")] + [post(id=i) for i in range(23)]}}).encode())

        with mock.patch.object(wtlive.urllib.request, "urlopen", fake):
            got = wtlive.feed("model", "downloads", 2, "ratte tiger!")
        self.assertEqual((sent["content"], sent["sort"], sent["page"], sent["searchString"]), (["model"], ["downloads"], ["2"], ["#ratte #tiger"]))
        self.assertEqual((len(got["posts"]), got["more"]), (24, True))  # 25 asked: there may be more

    def test_filters_it_doesnt_have_are_refused_before_asking(self):
        for args in (("video",), ("model", "random"), ("model", "created", -1)):
            with self.subTest(args), self.assertRaises(wtlive.LiveError):
                wtlive.feed(*args)

    def test_wt_live_out_of_reach(self):
        with mock.patch.object(wtlive.urllib.request, "urlopen", side_effect=urllib.error.URLError("down")), self.assertRaises(wtlive.LiveError) as e:
            wtlive.feed("model")
        self.assertEqual(e.exception.code, "offline")


class Fetch(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.object(mods, "STAGING", Path(tmp.name))
        patch.start()
        self.addCleanup(patch.stop)

    def redirect(self, to):
        headers = Message()
        headers["Location"] = to
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError(DL, 302, "Found", headers, io.BytesIO())
        return mock.patch.object(wtlive.urllib.request, "build_opener", return_value=opener)

    def test_a_posts_file_into_the_staging_folder(self):
        body = b"PK" + b"x" * 5000
        with self.redirect(CDN), mock.patch.object(wtlive.urllib.request, "urlopen", return_value=Response(body, {"Content-Length": str(len(body))})) as get:
            wtlive.fetch("abcdef", DL, "ratte_Beckett.zip")
        self.assertEqual(get.call_args[0][0].full_url, CDN)
        self.assertEqual((mods.STAGING / "abcdef" / "ratte_Beckett.zip").read_bytes(), body)
        self.assertEqual(wtlive.progress("abcdef"), {"done": 0, "size": 0})  # done with

    def test_only_from_wt_lives_own_servers(self):
        with self.assertRaises(wtlive.LiveError):
            wtlive.fetch("abcdef", "https://evil.example/dl/abcdefgh/", "x.zip")
        with self.redirect("https://evil.example/x.zip"), mock.patch.object(wtlive.urllib.request, "urlopen") as get, self.assertRaises(wtlive.LiveError):
            wtlive.fetch("abcdef", DL, "x.zip")
        get.assert_not_called()
        with self.assertRaises(wtlive.LiveError):
            wtlive.fetch("abcdef", DL, "../x.zip")

    def test_mods_limits_still_hold(self):
        with self.redirect(CDN), mock.patch.object(wtlive.urllib.request, "urlopen", return_value=Response(b"PK", {"Content-Length": str(mods.MAX_FILE + 1)})):
            with self.assertRaises(mods.ModsError) as e:
                wtlive.fetch("abcdef", DL, "big.zip")
        self.assertEqual(e.exception.code, "size")


class SightPacks(unittest.TestCase):
    def test_a_pack_into_the_library(self):  # a folder per vehicle; one name twice with another sight gets its folder's
        with tempfile.TemporaryDirectory() as d:
            user, z = Path(d) / "user", Path(d) / "pack.zip"
            with zipfile.ZipFile(z, "w") as a:
                a.writestr("Pack/germ_a/ger_sight.blk", "crosshair{ a:i=1 }")
                a.writestr("Pack/germ_b/ger_sight.blk", "crosshair{ b:i=2 }")
                a.writestr("Pack/germ_c/ger_sight.blk", "crosshair{ a:i=1 }")  # the same again
                a.writestr("Pack/readme.txt", "hi")
                a.writestr("Pack/empty.blk", "")
            got = sights.import_pack(user, z)
            self.assertEqual(got, ["lib/ger_sight.blk", "lib/germ_b_ger_sight.blk"])
            self.assertEqual(sorted(p.name for p in (user / "sights").iterdir()), ["ger_sight.blk", "germ_b_ger_sight.blk"])


if __name__ == "__main__":
    unittest.main()
