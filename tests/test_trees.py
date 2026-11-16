"""The research trees read by the builder: a folder the game names, and one it doesn't (the app names it by its vehicles)."""
import json
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest import mock

from wtftd import builder


class Trees(unittest.TestCase):
    def test_a_folder_without_a_name_gets_none(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dm = Path(tmp.name)
        (dm / "char.vromfs.bin_u" / "config").mkdir(parents=True)
        shop = {"country_germany": {"army": {"range": [{
            "germ_wwi_group": {"germ_a7v_event": {"rank": 1}, "germ_beutepanzer_mk_iv_event": {"rank": 1}},
            "germ_pzkpfw_38t_group": {"germ_pzkpfw_38t": {"rank": 1}}}]}}}
        (dm / "char.vromfs.bin_u" / "config" / "shop.blkx").write_text(json.dumps(shop), encoding="utf-8")
        lang = builder.Lang.__new__(builder.Lang)
        lang.all = {"shop/group/germ_pzkpfw_38t_group": {"en": "Pz.38(t) F/n.A."}}
        lang.lower, lang.out = {k.lower(): k for k in lang.all}, defaultdict(dict)
        known = {"germ_a7v_event", "germ_beutepanzer_mk_iv_event", "germ_pzkpfw_38t"}
        with mock.patch.object(builder, "DM", dm):
            trees = builder.build_trees(lang, known)
        self.assertEqual([x["g"] for x in trees["germany"]["ground"][0]], ["germ_wwi_group", "germ_pzkpfw_38t_group"])
        self.assertEqual(lang.out["units"], {"germ_pzkpfw_38t_group": {"en": "Pz.38(t) F/n.A."}})  # not "germ_a7v_event / ..."


if __name__ == "__main__":
    unittest.main()
