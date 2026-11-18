"""Guided weapon stats of the Best vehicles duels (wtftd/guidedstats.py), from made-up weapons page items read through
a vehicle's presets, ammunition or launchers, and an aircraft's BR in ground battles (wtftd/duelstats.py)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wtftd import armament, builder, duelstats, guidedstats

# armament.build_armament's items: c category, g guidance, rng range (m), lk / aa IR lock range from behind / from any
# side (m), ccm IRCCM, act active radar seeker, ins inertial guidance, ff fire-and-forget, pen penetration (mm), ship a
# seeker that locks on ships only
ITEMS = {i["id"]: i for i in (
    {"id": "aim_9m", "c": "aam_ir", "g": "ir", "rng": 18000, "lk": 11000, "aa": 3000, "ccm": 0.5},
    {"id": "aim_9l", "c": "aam_ir", "g": "ir", "rng": 18000, "lk": 11000, "aa": 3000},
    {"id": "aim_9b", "c": "aam_ir", "g": "ir", "rng": 11000, "lk": 6000},
    {"id": "aim_120", "c": "aam_radar", "g": "arh", "rng": 50000, "act": 1},
    {"id": "aim_7", "c": "aam_radar", "g": "sarh", "rng": 30000},
    {"id": "sidearm", "c": "aam_radar", "g": "arm", "rng": 18000},  # anti-radiation, with an air-to-air bullet type
    {"id": "aa_20", "c": "aam_radar", "g": "mclos", "rng": 4000},  # steered by hand
    {"id": "hellfire", "c": "atgm", "g": "laser", "rng": 8000, "pen": 1200},
    {"id": "ss_11", "c": "atgm", "g": "saclos", "rng": 3500},  # no penetration in its file
    {"id": "agm_45", "c": "agm", "g": "arm", "rng": 50000, "ff": 1},  # anti-radiation
    {"id": "agm_84d", "c": "agm", "g": "arh", "rng": 222000, "act": 1, "ff": 1, "ship": 1},  # anti-ship
    {"id": "penguin", "c": "agm", "g": "ir", "rng": 34000, "ff": 1, "ship": 1},  # anti-ship too
    {"id": "agm_65d", "c": "agm", "g": "ir", "rng": 26400, "pen": 830, "ff": 1},
    {"id": "gbu_12", "c": "gbomb", "g": "laser"},
    {"id": "apkws", "c": "agm", "g": "laser", "rng": 11000},
    {"id": "redeye", "c": "sam", "g": "ir", "rng": 10000, "lk": 5500},  # locks on from behind only
    {"id": "stinger", "c": "sam", "g": "ir", "rng": 10000, "lk": 11000, "aa": 5500},
    {"id": "python_5", "c": "sam", "g": "ir", "rng": 8000, "lk": 12000, "aa": 9000},
    {"id": "iris_t_sl", "c": "sam", "g": "ir", "rng": 40000, "lk": 12000, "aa": 9000, "ins": 1},  # locks on in flight
    {"id": "9m311", "c": "sam", "g": "saclos", "rng": 8000},
    {"id": "9m311_1m", "c": "sam", "g": "saclos", "rng": 10000},
    {"id": "mim146", "c": "sam", "g": "beam", "rng": 10000},  # ADATS
    {"id": "9m14", "c": "atgm", "g": "mclos", "rng": 3000, "pen": 400},  # Malyutka: steered by hand
    {"id": "tow", "c": "atgm", "g": "saclos", "rng": 3750, "pen": 630},
    {"id": "9m119", "c": "atgm", "g": "beam", "rng": 5000, "pen": 700},
    {"id": "mk15", "c": "torpedo", "g": "", "rng": 5500},
)}
BY_FILE = {f"w_{k}": [i] for k, i in ITEMS.items()}  # weapon file key -> the items it fires, with that file's stats


def opt(bullet: str, mod: str = "", x: bool = False, t: str = "atgm_tank", pen: int = 0) -> dict:
    """An ammo set of a ground vehicle's gun or launcher (vehicle_ammo): id "" is the default set, b its bullet names, t
    their types, s.pc a flat penetration curve."""
    return {"id": mod, "t": [t], "b": [bullet], **({"x": 1} if x else {}),
            **({"s": {"pc": [[10, pen], [4000, pen]]}} if pen else {})}


def group(cap: int, *opts, n: int = 1) -> dict:
    return {"trig": "gunner1", "cap": cap, "n": n, "opts": list(opts)}  # cap: rounds per barrel, n: barrels


def stats(c: str, presets=(), am=(), sp=None, sm=(), pods=None, ml=None, gw=()):
    """One vehicle of category c through guided_stats: its s, its su and what is left of its details. gw: details _gw, the
    launchers am leaves out, one list per fitted set (the unit's own, then each modification's that replaces it)."""
    rec = {"id": "v", "c": c, "s": {"spd": 100}, "su": {"spd": 90}}
    d = {"pr": [{"id": f"p{i}", "w": w} for i, w in enumerate(presets)], "am": list(am), "_sm": list(sm),
         "_ml": ml or {}, "_gw": list(gw)}
    if sp is not None:
        d["_sp"] = [f"p{i}" for i in sp]
    guidedstats.guided_stats([rec], {"v": d}, ITEMS, BY_FILE, pods or {})
    return rec["s"], rec["su"], d


class GuidedStats(unittest.TestCase):
    def test_aam_counts_and_kinds(self):
        s, _, _ = stats("air", [[["w_aim_9m", 4]], [["w_aim_9b", 2], ["w_aim_120", 2]], [["w_aim_7_default", 1]]])
        self.assertEqual((s["ir"], s["irq"], s["rm"], s["rmq"], s["rmr"]), (4, 3, 2, 2, 50))  # most in one preset, best
        self.assertEqual(stats("heli", [[["w_aim_9b", 2]]])[0]["irq"], 1)  # rear-aspect only
        self.assertEqual(stats("heli", [[["w_aim_9l", 2]]])[0]["irq"], 2)  # all-aspect, no IRCCM
        self.assertEqual(stats("air", [[["w_aim_7", 2]]])[0]["rmq"], 1)  # semi-active
        self.assertEqual(stats("air", [[["w_aim_7_default", 2]]])[0]["rm"], 2)  # a weapon file's variant
        self.assertNotIn("rm", stats("heli", [[["w_aim_120", 2]]])[0])  # radar AAMs: aircraft only
        self.assertNotIn("rm", stats("air", [[["w_sidearm", 2], ["w_aa_20", 2]]])[0])  # anti-radiation, steered by hand

    def test_guided_ground_weapons(self):
        s, _, _ = stats("heli", [[["w_hellfire", 8], ["w_agm_45", 2], ["w_agm_84d", 2]]])
        self.assertEqual((s["atg"], s["atr"], s["atp"], s["atq"]), (8, 8000, 1200, 1))
        s, _, _ = stats("air", [[["w_agm_65d", 6]]])
        self.assertEqual((s["atg"], s["atr"], s["atq"]), (6, 10000, 2))  # its 26.4 km is a flight range: capped
        self.assertNotIn("atp", s)  # helicopters and ground vehicles only
        s, _, _ = stats("air", [[["w_gbu_12", 4]]])
        self.assertEqual((s["atg"], s["atr"]), (4, 8000))  # a guided bomb without a range
        self.assertNotIn("atg", stats("air", [[["w_agm_45", 2], ["w_agm_84d", 2], ["w_penguin", 2]]])[0])  # not on tanks
        s, _, _ = stats("air", [[["lau_131", 12]]], pods={"lau_131": ("w_apkws", 7)})  # pods of 7 guided rockets
        self.assertEqual(s["atg"], 84)
        s, _, _ = stats("heli", [[["w_ss_11", 4]]])
        self.assertEqual((s["atg"], s["atr"]), (4, 3500))
        self.assertNotIn("atp", s)  # no penetration known: no 0 written
        s, _, _ = stats("heli", [[["w_9m14", 4]]])
        self.assertEqual((s["atg"], s["atr"], s["atp"]), (4, 3000, 400))  # steered by hand, still a guided missile

    def test_sam_reach(self):
        # an IR SAM that locks on before launch: how far it locks on from any side (aa), else from behind (lk), no farther
        # than it flies; one that locks on in flight and the other SAMs: their range
        for bullet, reach in (("Stinger", 5500), ("redeye", 5500), ("python_5", 8000), ("iris_t_sl", 40000),
                              ("9m311", 8000)):
            self.assertEqual(stats("ground", am=[group(4, opt(bullet, t="sam_tank"))])[0]["sam"], reach, bullet)

    def test_torpedoes(self):
        s, _, _ = stats("ship", [[["w_mk15", 10]], []])
        self.assertEqual((s["tor"], s["torr"]), (10, 5500))

    def test_ground_launcher_and_gun_atgm(self):
        gun = group(40, opt("apfsds"), opt("9m119", mod="atgm"))  # a gun-launched missile: the gun's rounds
        launcher = group(2, opt("tow"), n=2)
        s, _, _ = stats("ground", am=[gun, launcher])
        self.assertEqual((s["atg"], s["atr"], s["atp"], s["atq"]), (44, 5000, 700, 1))
        self.assertEqual((stats("ground", am=[launcher])[0]["atr"], stats("ground", am=[gun])[0]["atr"]), (3750, 5000))
        self.assertNotIn("atg", stats("ground", am=[group(40, opt("9m119", mod="atgm", x=True))])[0])  # not normally

    def test_gun_missiles_per_spawn(self):
        # no more of a gun's missiles than a spawn may carry (wpcost maxToRespawn, details _ml); a belt's limit is not one
        gun = group(44, opt("he", mod="belt", t="he_frag"), opt("9m119", mod="atgm"))
        for ml, atg in (({"atgm": 4}, 4), ({"atgm": 4, "belt": 1}, 4), ({"belt": 1}, 44)):
            self.assertEqual(stats("ground", am=[gun], ml=ml)[0]["atg"], atg, ml)
        two = group(48, opt("9m119", mod="atgm"), opt("tow", mod="atgm_2"))
        self.assertEqual(stats("ground", am=[two], ml={"atgm": 8, "atgm_2": 8})[0]["atg"], 16)  # 8 of each
        self.assertEqual(stats("ground", am=[two], ml={"atgm": 8})[0]["atg"], 48)  # one has no limit: the whole load
        # a launcher without an ammo set adds its rounds to the gun's missiles
        self.assertEqual(stats("ground", am=[gun], ml={"atgm": 4}, gw=[[["w_tow", 5]]])[0]["atg"], 9)

    def test_dual_purpose_missile(self):
        # ADATS: its SAM fired from an ATGM set is an anti-tank missile too, with the set's shaped charge
        s, _, _ = stats("ground", am=[group(8, opt("mim146", pen=900))])
        self.assertEqual((s["sam"], s["atg"], s["atr"], s["atp"]), (10000, 8, 10000, 900))
        self.assertNotIn("atg", stats("ground", am=[group(8, opt("mim146", t="sam_tank", pen=900))])[0])

    def test_launchers_without_ammo_sets(self):
        # an M113's TOW or a BMP-1's Malyutka: a launcher whose file has no ammo set is not in am but in details _gw
        s, su, d = stats("ground", am=[group(600, opt("12_7mm", t="ap_i_t"))], gw=[[["w_tow", 5], ["w_tow", 5]]])
        self.assertEqual((s["atg"], s["atr"], s["atp"]), (10, 3750, 630))  # the rounds of every block
        self.assertEqual(su, {"spd": 90})  # fitted: the stock vehicle has it
        self.assertNotIn("_gw", d)

    def test_modification_launchers(self):
        # a modification that replaces the fitted weapons (effects commonWeapons: the BMP-1P turret's Konkurs, the 2S6's
        # 9M311-1M) fits its launcher upgraded; the stock vehicle keeps its own
        s, su, _ = stats("ground", gw=[[["w_9m14", 4]], [["w_tow", 5]]])
        self.assertEqual(({k: s[k] for k in ("atg", "atr", "atp")}, su), ({"atg": 5, "atr": 3750, "atp": 630},
                                                                          {"spd": 90, "atg": 4, "atr": 3000, "atp": 400}))
        s, su, _ = stats("ground", am=[group(8, opt("9m311", t="sam_tank"))], gw=[[], [["w_9m311_1m", 8]]])
        self.assertEqual((s["sam"], su["sam"]), (10000, 8000))
        self.assertEqual(stats("ground", gw=[[], [["w_tow", 5]]])[1], {"spd": 90, "atg": 0, "atr": 0, "atp": 0, "atq": 0})

    def test_stock_values(self):
        # p0 needs a modification (not in _sp): the stock aircraft carries p1 only
        s, su, d = stats("air", [[["w_aim_9m", 4], ["w_agm_65d", 2]], [["w_aim_9b", 2]]], sp=[1])
        self.assertEqual((s["spd"], s["ir"], s["irq"], s["atg"]), (100, 4, 3, 2))  # the record's other stats stay
        self.assertEqual(su, {"spd": 90, "ir": 2, "irq": 1, "atg": 0, "atr": 0, "atq": 0})  # what the stock lacks: 0
        self.assertEqual(set(d), {"pr", "am"})  # the lists for guided_stats never reach details.json
        self.assertEqual(stats("air", [[["w_aim_9m", 4]], []])[1], {"spd": 90})  # no stock list: every preset is stock
        # ground: the default set and the free ammo (_sm) are stock, the researched missile is not
        am = [group(40, opt("apfsds"), opt("9m119", mod="atgm")), group(2, opt("tow", mod="tow_free"))]
        _, su, _ = stats("ground", am=am, sm=["tow_free"])
        self.assertEqual(su, {"spd": 90, "atg": 2, "atr": 3750, "atp": 630})

    def test_missile_carrier_speed(self):
        # a missile carrier (gl: no shell, so no vel) gets its main weapon's fastest guided missile (SS.11 220, TOW 296 m/s),
        # not a faster one of a launcher beside it (9M119 350); su.vel from its stock missiles, None when it has none in stock
        items = {**ITEMS, **{k: {**ITEMS[k], "v": v} for k, v in (("ss_11", 220), ("tow", 296), ("9m119", 350))}}

        def carrier(*opts, sm=(), s=None):
            rec = {"id": "v", "c": "ground", "s": {"gl": 1} if s is None else s}
            d = {"am": [{"trig": "gunner0", "wi": 1, "cap": 4, "n": 1, "opts": list(opts)}], "_sm": list(sm),
                 "_gw": [[["w_9m119", 2]]]}
            guidedstats.guided_stats([rec], {"v": d}, items, {**BY_FILE, "w_9m119": [items["9m119"]]})
            return rec["s"].get("vel"), (rec.get("su") or {}).get("vel", "same")

        self.assertEqual(carrier(opt("ss_11"), opt("tow", mod="tow"), opt("9m119", mod="b", x=True)), (296, 220))
        self.assertEqual(carrier(opt("ss_11"), opt("tow", mod="tow"), sm=["tow"]), (296, "same"))
        self.assertEqual(carrier(opt("tow", mod="tow")), (296, None))
        self.assertEqual(carrier(opt("tow"), s={}), (None, "same"))  # not a missile carrier: no vel from its missiles

    def test_missile_launcher_am_leaves_out(self):
        # M113A1 (TOW): no main gun among its ammo groups (its M2 is none), its TOW launcher has no ammo set: a missile
        # carrier, vel its fastest missile, upgraded with a modification's launcher too (_gw); not an unguided rocket's
        by_file = {**BY_FILE, "w_ss_11": [{**ITEMS["ss_11"], "v": 220}], "w_tow": [{**ITEMS["tow"], "v": 296}],
                   "w_rockets": [{"id": "r", "c": "rocket", "g": "", "v": 700}]}

        def launchers(*gw):
            rec = {"id": "v", "c": "ground", "s": {"rel": 10}}
            guidedstats.guided_stats([rec], {"v": {"am": [], "_gw": list(gw)}}, ITEMS, by_file)
            return rec["s"].get("gl"), rec["s"].get("vel"), (rec.get("su") or {}).get("vel", "same")

        self.assertEqual(launchers([["w_tow", 10]]), (1, 296, "same"))
        self.assertEqual(launchers([["w_ss_11", 4]], [["w_tow", 5]]), (1, 296, 220))
        self.assertEqual(launchers([["w_tow", 10], ["w_rockets", 30]]), (1, 296, "same"))  # its faster rockets: no missile
        # Type 75 MLRS: no missile carrier (its rockets stand in for a main gun in the builder: unguided_launcher)
        self.assertEqual(launchers([["w_rockets", 30]]), (None, None, "same"))

    def test_ground_battle_br(self):
        self.assertEqual(duelstats.ground_battle_br({"economicRankTankHistorical": 26}, [10.7, 10.3, 10.7]), [10.7, 9.7, 10.7])
        self.assertEqual(duelstats.ground_battle_br({"economicRankTankSimulation": 26}, [10.7, 10.3, 10.7]), [10.7, 10.3, 9.7])
        self.assertIsNone(duelstats.ground_battle_br({"economicRankHistorical": 28}, [10.7, 10.3, 10.7]))
        self.assertIsNone(duelstats.ground_battle_br({"economicRankTankHistorical": 28}, [10.7, 10.3, 10.7]))  # the same


class Wiring(unittest.TestCase):
    def test_armament_index(self):  # what build_armament gives guided_stats: the items, each file's own ones, pods
        with tempfile.TemporaryDirectory() as tmp:
            dm, data = Path(tmp) / "dm", Path(tmp) / "data"
            weapons = dm / "aces.vromfs.bin_u" / "gamedata" / "weapons"
            for folder in (weapons / "rocketguns", weapons / "containers", data):
                folder.mkdir(parents=True)

            def rocket(stem: str, bullet: str, **fields):
                fields = {"bulletName": bullet, "bulletType": "rocket_aircraft", "guidanceType": "laser", "guidance": {}, **fields}
                (weapons / "rocketguns" / f"{stem}.blkx").write_text(json.dumps({"rocket": fields}))

            rocket("us_apkws_m151", "us_apkws_m151", maxDistance=11000.0)
            rocket("spike_er", "spike_er", maxDistance=8000.0)
            rocket("spike_nlos", "spike_er", maxDistance=32000.0)  # another file of the same missile, farther
            rocket("us_agm_84d", "us_agm_84d", guidanceType="radar", maxDistance=222000.0,
                   guidance={"radarSeeker": {"active": True, "targetRadiusMin": 15.0}})  # takes nothing smaller than a ship
            for stem, least in (("us_agm_65d", 1.5), ("us_agm_119a_penguin", 10.0)):  # locks on tanks; ships only
                rocket(stem, stem, guidanceType="optical", guidance={"opticalSeeker": {"targetRadiusMin": least}})
            pod = {"container": True, "blk": "gameData/Weapons/rocketGuns/us_apkws_m151.blk", "bullets": 7}
            (weapons / "containers" / "lau_131.blkx").write_text(json.dumps(pod))
            index = {}
            with mock.patch.object(builder, "DM", dm), mock.patch.object(armament, "DATA", data):
                armament.build_armament(builder.Lang(), [{"id": "a_10c", "c": "air", "br": [9.0, 9.0, 9.0], "wp": ["lau_131"]}],
                                        None, index)
        by_file = index["by_file"]
        self.assertEqual(index["pods"], {"lau_131": ("us_apkws_m151", 7)})
        self.assertEqual([(i["id"], i["c"], i["rng"]) for i in by_file["us_apkws_m151"]], [("us_apkws_m151", "agm", 11000)])
        self.assertEqual((by_file["spike_er"][0]["rng"], by_file["spike_nlos"][0]["rng"]), (8000, 32000))  # each its own
        self.assertEqual((by_file["us_agm_84d"][0]["g"], by_file["us_agm_84d"][0].get("ship")), ("arh", 1))
        self.assertEqual([by_file[k][0].get("ship") for k in ("us_apkws_m151", "us_agm_65d", "us_agm_119a_penguin")],
                         [None, None, 1])
        self.assertEqual(index["items"]["us_apkws_m151"]["c"], "agm")

    def test_build_vehicles_gives_what_they_read(self):
        # an aircraft's ground-battle BR; a ground vehicle's launcher without an ammo set and its missiles' per-spawn
        # limits, read by guided_stats through the weapons page's index; an ammo set one of its modifications gives under
        # another name (the shared modification table's additiveBulletMod) is normally available
        with tempfile.TemporaryDirectory() as tmp:
            dm, data = Path(tmp) / "dm", Path(tmp) / "data"
            game = dm / "aces.vromfs.bin_u" / "gamedata"
            for folder in (dm / "char.vromfs.bin_u" / "config", game / "units" / "tankmodels", game / "flightmodels",
                           game / "weapons" / "groundmodels_weapons", data):
                folder.mkdir(parents=True)
            wp = {"jet": {"unitMoveType": "air", "unitClass": "exp_assault", "rank": 7, "economicRankArcade": 27,
                          "economicRankHistorical": 28, "economicRankSimulation": 27, "economicRankTankHistorical": 26},
                  "tow_carrier": {"unitMoveType": "tank", "unitClass": "exp_tank_destroyer", "rank": 4,
                                  "modifications": {"100mm_atgm": {"tier": 0, "value": 0, "maxToRespawn": 4},
                                                    "tow_2": {"tier": 2, "value": 900}, "12mm_ap": {"tier": 1, "value": 50}}}}
            (dm / "char.vromfs.bin_u" / "config" / "wpcost.blkx").write_text(json.dumps(wp))
            (dm / "char.vromfs.bin_u" / "config" / "modifications.blkx").write_text(json.dumps(
                {"modifications": {"12mm_ap": {"effects": {"additiveBulletMod": "12mm_ussr_ap"}}}}))
            (game / "flightmodels" / "jet.blkx").write_text("{}")

            def guns(launcher: str) -> dict:
                return {"Weapon": [{"blk": f"gameData/Weapons/groundModels_weapons/{k}.blk", "bullets": n}
                                   for k, n in (("mg", 600), (launcher, 10))]}
            # its TOW-2 modification replaces the fitted weapons (effects commonWeapons)
            unit = {"commonWeapons": guns("tow_launcher"),
                    "modifications": {"tow_2": {"effects": {"commonWeapons": guns("tow_2_launcher")}}}}
            (game / "units" / "tankmodels" / "tow_carrier.blkx").write_text(json.dumps(unit))
            (game / "weapons" / "groundmodels_weapons" / "mg.blkx").write_text(json.dumps(
                {"bullet": {"bulletName": "12mm_ball"}, "12mm_ussr_ap": {"bullet": {"bulletName": "12mm_ap"}}}))
            for stem, rng in (("tow", 3750.0), ("tow_2", 4000.0)):
                rocket = {"bulletName": stem, "bulletType": "atgm_tank", "guidanceType": "saclos", "maxDistance": rng}
                (game / "weapons" / "groundmodels_weapons" / f"{stem}_launcher.blkx").write_text(json.dumps({"rocket": rocket}))
            index = {}
            with mock.patch.object(builder, "DM", dm), mock.patch.object(builder, "DATA", data), \
                    mock.patch.object(armament, "DATA", data), mock.patch.object(builder, "_GLOBAL_MODS", None):
                vehicles, details = builder.build_vehicles(builder.Lang())
                armament.build_armament(builder.Lang(), vehicles, None, index)
        rec = {v["id"]: v for v in vehicles}
        self.assertEqual(rec["jet"]["bt"], [10.0, 9.7, 10.0])
        tank = details["tow_carrier"]
        self.assertEqual(([g["w"] for g in tank["am"]], tank["_gw"], tank["_ml"]),
                         (["mg"], [[["tow_launcher", 10]], [["tow_2_launcher", 10]]], {"100mm_atgm": 4}))
        self.assertEqual([(o["id"], o.get("x")) for o in tank["am"][0]["opts"]], [("", None), ("12mm_ussr_ap", None)])
        guidedstats.guided_stats(vehicles, details, index["items"], index["by_file"], index["pods"])
        tow = rec["tow_carrier"]
        self.assertEqual((tow["s"]["atg"], tow["s"]["atr"], tow["su"]["atr"]), (10, 4000, 3750))
        self.assertFalse({"_sp", "_sm", "_gw", "_ml"} & set(tank))

    def test_the_build_writes_them_and_drops_the_stock_lists(self):
        rec = {"id": "jet", "c": "air", "n": "usa", "r": 7, "br": [12.0, 12.0, 12.0], "s": {"spd": 1400}}
        details = {"jet": {"pr": [{"id": "p", "w": [["w_aim_9m", 2]]}], "_sp": ["p"], "_sm": [], "_gw": [], "_ml": {}}}
        lang = mock.Mock()
        lang.write.side_effect = lambda: ["en"]

        def build_armament(lang, vehicles, progress, index):
            index.update(items=ITEMS, by_file=BY_FILE)

        with tempfile.TemporaryDirectory() as tmp:
            data, dm = Path(tmp) / "data", Path(tmp) / "dm"
            dm.mkdir()
            steps = {name: mock.Mock(return_value=value) for name, value in (
                ("Lang", lang), ("build_vehicles", ([rec], details)), ("build_levels", {}), ("build_scenarios", []),
                ("build_trees", {}), ("apply_rarity", None), ("build_bullet_icons", {}), ("build_battle_words", {}),
                ("build_bases", {}), ("build_difficulty", None))}
            with mock.patch.multiple(builder, DATA=data, DM=dm, **steps), mock.patch.object(armament, "build_armament", build_armament):
                builder._build(None, "game", history=False)
            written = json.loads((data / "details.json").read_text())
            vehicles = json.loads((data / "vehicles.json").read_text())
        self.assertEqual(written, {"jet": {"pr": [{"id": "p", "w": [["w_aim_9m", 2]]}]}})
        self.assertEqual((vehicles[0]["s"]["ir"], vehicles[0]["s"]["irq"]), (2, 3))


class Guards(unittest.TestCase):
    def test_a_vehicle_that_fails_loses_its_guided_keys_only(self):
        # an ammo group without its count of rounds: logged, no guided key; the next vehicle gets its own, and neither
        # record keeps the lists build_vehicles left for guided_stats
        bad, good = {"id": "bad", "c": "ground", "s": {"spd": 50}}, {"id": "good", "c": "air", "s": {"spd": 900}}
        details = {"bad": {"am": [{"opts": [opt("tow")]}], "_sp": [], "_sm": [], "_gw": [], "_ml": {}},
                   "good": {"pr": [{"id": "p", "w": [["w_aim_9m", 2]]}], "_sp": ["p"], "_sm": [], "_gw": [], "_ml": {}}}
        with mock.patch.object(guidedstats, "log") as log:
            guidedstats.guided_stats([bad, good], details, ITEMS, BY_FILE)
        self.assertEqual((bad["s"], good["s"]["ir"]), ({"spd": 50}, 2))
        self.assertEqual({k: set(d) for k, d in details.items()}, {"bad": {"am"}, "good": {"pr"}})
        self.assertIn("bad", log.call_args[0][0])

    def test_build_vehicles_keeps_a_vehicle_whose_duel_stats_fail(self):
        # shapes not seen yet, read by the helpers the duel stats share with the lists left for guided_stats: an
        # aircraft's slot preset that needs a block (preset_is_stock), a tank modification's weapon naming its slot
        # preset by a list (fitted_sets)
        with tempfile.TemporaryDirectory() as tmp:
            dm, data = Path(tmp) / "dm", Path(tmp) / "data"
            config, game = dm / "char.vromfs.bin_u" / "config", dm / "aces.vromfs.bin_u" / "gamedata"
            for folder in (config, game / "flightmodels" / "weaponpresets", game / "units" / "tankmodels", data):
                folder.mkdir(parents=True)
            (config / "wpcost.blkx").write_text(json.dumps({
                "jet": {"unitMoveType": "air", "unitClass": "exp_fighter"},
                "tank": {"unitMoveType": "tank", "unitClass": "exp_tank", "modifications": {"m": {"tier": 1}}}}))
            (config / "unittags.blkx").write_text(json.dumps({"jet": {"Shop": {"maxSpeed": 250}}}))
            jet = {"weapon_presets": {"preset": [{"name": "p", "blk": "gameData/FlightModels/weaponPresets/jet_p.blk"}]},
                   "WeaponSlots": {"WeaponSlot": [{"index": 1, "WeaponPreset": [{"name": "x", "reqModification": {"m": 1}}]}]}}
            (game / "flightmodels" / "jet.blkx").write_text(json.dumps(jet))
            (game / "flightmodels" / "weaponpresets" / "jet_p.blkx").write_text(json.dumps({"Weapon": [{"slot": 1, "preset": "x"}]}))
            tank = {"modifications": {"m": {"effects": {"commonWeapons": {"Weapon": [{"slot": 1, "preset": ["x"]}]}}}}}
            (game / "units" / "tankmodels" / "tank.blkx").write_text(json.dumps(tank))
            with mock.patch.object(builder, "DM", dm), mock.patch.object(builder, "DATA", data), \
                    mock.patch.object(builder, "_GLOBAL_MODS", {}), mock.patch.object(builder, "log") as log:
                vehicles, details = builder.build_vehicles(builder.Lang())
        rec = {v["id"]: v for v in vehicles}
        self.assertEqual((set(rec), set(details), rec["jet"]["s"]["spd"]), ({"jet", "tank"}, {"jet", "tank"}, 900))  # card stats stay
        self.assertEqual(sorted(c.args[0].split(":")[0].strip() for c in log.call_args_list if "no duel stats" in c.args[0]),
                         ["jet", "tank"])


if __name__ == "__main__":
    unittest.main()
