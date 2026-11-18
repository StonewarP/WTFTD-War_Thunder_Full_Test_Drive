"""Stats the Best vehicles duels read for aircraft, helicopters, SPAA and ships (wtftd/duelstats.py), from made-up unit
and weapon files: forward guns and gun pods, payload with rocket pods, countermeasures, sensors, turrets, what a stock
vehicle has, a ship's main battery, and the pod masses of the weapons catalog."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wtftd import builder, duelstats


class Files:
    """Stands in for builder.WeaponCache: get(blk) gives the made-up file of that name."""
    def __init__(self, **files):
        self.files = {k.lower(): v for k, v in files.items()}

    def get(self, blk: str):
        return self.files.get(blk.lower())


def gun(shot_freq: float, *masses: float) -> dict:
    """A gun file: shots/s per barrel and its default belt."""
    return {"shotFreq": shot_freq, "bullet": [{"mass": m} for m in masses]}


def weapon(trigger: str, blk: str, **kw) -> dict:
    return {"trigger": trigger, "blk": blk, **kw}


def unit(fitted=(), presets=(), slots=()) -> dict:
    """A unit file: fitted weapons (commonWeapons), weapon presets [(name, file)], WeaponSlots."""
    u = {"commonWeapons": {"Weapon": list(fitted)}, "weapon_presets": {"preset": [{"name": n, "blk": b} for n, b in presets]}}
    if slots:
        u["WeaponSlots"] = {"WeaponSlot": list(slots)}
    return u


def air(cat: str, u: dict, wc: Files, presets=(), catalog=None, sy=None, lim=None, mods=()) -> tuple[dict, dict]:
    """presets: build_vehicles' list ({id, w, s: {slot: slot preset}, req}); mods: the modifications it can research."""
    return duelstats.air_stats(cat, u, wc, list(presets), catalog or {}, sy or {}, lim or {}, mods)


class Guns(unittest.TestCase):
    def test_gun_burst_forward_only(self):
        wc = Files(**{"cannon.blk": gun(10, 0.1, 0.2), "turret.blk": gun(20, 0.05)})
        u = unit([weapon("cannon", "cannon.blk"), weapon("gunner0", "turret.blk"),
                  weapon("additional gun", "cannon.blk", schraegeMusikAngle=70)])  # Schraege Musik: it fires upward
        self.assertEqual(air("air", u, wc)[0]["fg"], 1.5)
        self.assertEqual(air("heli", u, wc)[0]["fg"], 2.5)  # a helicopter's gunner0 is its chin gun

    def test_modification_replaces_fitted_weapons(self):
        # Yak-9UT: a modification swaps the NS-23 for an N-37; Eurofighter: one swaps the gun's slot preset for one
        # with more flares. Researched: the upgraded vehicle may fit them, the stock one has the unit's own.
        wc = Files(**{"ns23.blk": gun(10, 0.2), "n37.blk": gun(7, 0.7)})
        n37 = {"Weapon": [weapon("cannon", "n37.blk"), weapon("countermeasures", "cm.blk", bullets=320)]}
        u = {**unit([weapon("cannon", "ns23.blk"), weapon("countermeasures", "cm.blk", bullets=32)]),
             "modifications": {"n37_mod": {"effects": {"commonWeapons": n37}},
                               "not_researchable": {"effects": {"commonWeapons": {"Weapon": [weapon("cannon", "n37.blk")] * 9}}}}}
        s, su = air("air", u, wc, mods={"n37_mod"})
        self.assertEqual((s["fg"], s["cm"], su["fg"], su["cm"]), (4.9, 320, 2.0, 32))
        self.assertEqual(air("air", u, wc)[0]["fg"], 2.0)  # nothing researchable

    def test_weapon_shotfreq_override(self):
        wc = Files(**{"cannon.blk": gun(10, 0.2), "dummy.blk": gun(10, 0.2), "launcher.blk": {"shotFreq": 1, "bullet": [{"mass": 18.5, "rocket": {}}]}})
        weapons = [weapon("cannon", "cannon.blk", shotFreq=5), weapon("cannon", "dummy.blk", dummy=True),
                   weapon("cannon", "launcher.blk")]  # a dummy and a missile launcher fire nothing here
        self.assertEqual(duelstats.gun_burst(weapons, wc), 1.0)

    def test_gun_pod_best_preset(self):
        wc = Files(**{"cannon.blk": gun(10, 0.1, 0.2), "pod.blk": gun(10, 0.1), "default.blk": {},
                      "gun_pods.blk": {"Weapon": [weapon("additional gun", "pod.blk", external=True)]}})
        u = unit([weapon("cannon", "cannon.blk")], [("default", "default.blk"), ("gun_pods", "gun_pods.blk")])
        s, su = air("air", u, wc, [{"id": "default", "w": []}, {"id": "gun_pods", "w": [["pod", 1]], "req": "gun_pods"}])
        self.assertEqual((s["fg"], su["fg"]), (2.5, 1.5))  # the pods' preset needs a modification

    def test_guns_only_in_presets(self):
        # Javelin FAW.9: no fitted gun, four ADEN in most presets, two in one
        wc = Files(**{"aden.blk": gun(20, 0.26), "four.blk": {"Weapon": [weapon("cannon", "aden.blk")] * 4},
                      "two.blk": {"Weapon": [weapon("cannon", "aden.blk")] * 2}})
        u = unit((), [("four", "four.blk"), ("two", "two.blk")])
        s, su = air("air", u, wc, [{"id": "four", "w": []}, {"id": "two", "w": []}])
        self.assertEqual(s["fg"], 20.8)
        self.assertNotIn("fg", su)

    def test_defensive_turrets(self):
        wc = Files(**{"mg.blk": gun(15, 0.03)})
        u = unit([weapon("gunner0", "mg.blk"), weapon("gunner1", "mg.blk"), weapon("gunner1", "mg.blk"),
                  weapon("machine gun", "mg.blk"), weapon("gunner2", "optic.blk", dummy=True)])
        self.assertEqual(air("air", u, wc)[0]["def"], 2)
        self.assertNotIn("def", air("heli", u, wc)[0])  # a helicopter's gunners are its chin and flexible forward guns

    def test_spaa_burst(self):
        wc = Files(**{"35mm.blk": gun(10, 0.2), "sam.blk": {"shotFreq": 1, "bullet": [{"mass": 18.5, "rocket": {}}]}})
        u = unit([weapon("gunner0", "35mm.blk"), weapon("gunner0", "35mm.blk"), weapon("gunner1", "sam.blk"),
                  weapon("gunner2", "dummy_weapon.blk", dummy=True)])
        self.assertEqual(duelstats.spaa_stats(u, wc), ({"aab": 4.0}, {}))
        self.assertEqual(duelstats.spaa_stats(unit([weapon("gunner0", "sam.blk")]), wc), ({}, {}))  # missiles only
        u["modifications"] = {"guns": {"effects": {"commonWeapons": {"Weapon": [weapon("gunner0", "35mm.blk")] * 3}}}}
        self.assertEqual(duelstats.spaa_stats(u, wc, {"guns"}), ({"aab": 6.0}, {"aab": 4.0}))


class Loads(unittest.TestCase):
    CATALOG = {"bomb_250": {"c": "bombs", "m": 250}, "rocket_pod": {"c": "rockets", "m": 157.8, "pod": 19},
               "fuel_tank": {"c": "fuel", "m": 300}, "aim_9": {"c": "aam_ir", "m": 85}}

    def test_payload_with_pods(self):
        pod = weapon("rockets", "gameData/Weapons/containers/rocket_pod.blk", external=True, bullets=19)  # its own rockets
        slots = [{"index": 1, "WeaponPreset": [{"name": "bombs", "Weapon": [weapon("bombs", "bomb_250.blk", bullets=2)]}]},
                 {"index": 2, "WeaponPreset": [{"name": "pods", "reqModification": "rocket_pods", "Weapon": [pod, pod]},
                                               {"name": "tanks", "Weapon": [weapon("fuel", "fuel_tank.blk"), weapon("aam", "aim_9.blk")]}]}]
        wc = Files(**{"strike.blk": {"Weapon": [{"slot": 1, "preset": "bombs"}, {"slot": 2, "preset": "pods"}]},
                      "ferry.blk": {"Weapon": [{"slot": 1, "preset": "bombs"}, {"slot": 2, "preset": "tanks"}]}})
        u = unit((), [("strike", "strike.blk"), ("ferry", "ferry.blk")], slots)
        strike = {"id": "strike", "w": [["bomb_250", 2], ["ffar", 38]], "s": {"1": "bombs", "2": "pods"}}
        ferry = {"id": "ferry", "w": [["bomb_250", 2], ["fuel_tank", 1], ["aim_9", 1]], "s": {"1": "bombs", "2": "tanks"}}
        s, su = air("air", u, wc, [strike, ferry], self.CATALOG)
        self.assertEqual((s["pay"], su["pay"]), (815.6, 500))  # fuel tanks and missiles are no payload
        self.assertFalse(duelstats.preset_is_stock(strike, u))  # one of its slot presets needs a modification
        self.assertTrue(duelstats.preset_is_stock(ferry, u))
        self.assertFalse(duelstats.preset_is_stock({"id": "x", "w": [], "req": "x"}, u))

    def test_rack_of_pods(self):
        # a triple ejector rack holding three pods: in no catalog, its own mass and its pods'
        wc = Files(**{"gameData/Weapons/containers/ter_rocket_pod.blk": {"container": True, "blk": "gameData/Weapons/containers/rocket_pod.blk",
                                                                          "bullets": 3, "mass": 40},
                      "p.blk": {"Weapon": [weapon("rockets", "gameData/Weapons/containers/ter_rocket_pod.blk", external=True)]}})
        s, _ = air("heli", unit((), [("p", "p.blk")]), wc, [{"id": "p", "w": [["rocket_pod", 3]]}], self.CATALOG)
        self.assertEqual(s["pay"], 513.4)

    def test_countermeasures_with_pods(self):
        slots = [{"index": 5, "WeaponPreset": [{"name": "cm_pod", "Weapon": [weapon("countermeasures", "cm.blk", bullets=30)]}]}]
        wc = Files(**{"p.blk": {"Weapon": [{"slot": 5, "preset": "cm_pod"}]}, "clean.blk": {}})
        u = unit([weapon("countermeasures", "cm.blk", bullets=60)], [("p", "p.blk"), ("clean", "clean.blk")], slots)
        s, su = air("air", u, wc, [{"id": "p", "w": [], "s": {"5": "cm_pod"}, "req": "cm_pods"}, {"id": "clean", "w": []}])
        self.assertEqual((s["cm"], su["cm"]), (90, 60))


class Sensors(unittest.TestCase):
    def test_sensors(self):
        sy = {"se": [["apg", "radar", {"k": "radar", "r": 54000, "ro": "st"}], ["laser", "radar", {"r": 9000, "ro": "rf"}],
                     ["alr", "rwr", {"r": 50000}]], "su": {"se": [["alr", "rwr", {"r": 50000}]]}}
        s, su = air("air", unit(), Files(), sy=sy)
        self.assertEqual((s["rad"], s["rwr"]), (54, 1))
        self.assertEqual(su, {"rad": 0})  # the stock aircraft has its warning receiver, not its radar
        s, _ = air("air", unit(), Files(), sy={"se": [["laser", "radar", {"r": 9000, "ro": "rf"}]]})
        self.assertNotIn("rad", s)  # a range finder does not search
        self.assertNotIn("rwr", s)

    def test_radar_range_against_aircraft(self):
        # the radar's file: transceivers, signals (what each can see) and the fsm setting a transceiver with a signal
        def radar(transivers: dict, signals: dict, sets: dict) -> dict:
            return {"transivers": {k: {"range": r} for k, r in transivers.items()}, "signals": signals,
                    "fsms": {"main": {"actionsTemplates": {k: {**({"setTransiver": {"transiver": t}} if t else {}),
                                                                **({"setSignal": {"signal": g}} if g else {})}
                                                           for k, (t, g) in sets.items()}}}}
        sea = {"aircraftAsTarget": False, "shipsAsTarget": True}
        wc = Files(**{"gameData/sensors/ps_37a.blk": radar({"lprf": 70000, "sea": 100000}, {"lprfSearch": {}, "seaSearch": sea},
                                                           {"a": ("lprf", "lprfSearch"), "s": ("sea", "seaSearch")}),
                      "gameData/sensors/ari_5390.blk": radar({"common": 278000}, {"search": sea}, {"i": ("common", ""), "s": ("", "search")}),
                      # a transceiver set on its own, its signals elsewhere (PS-011): it counts
                      "gameData/sensors/ps_011.blk": radar({"radar": 30000, "irst": 16000}, {"searchRadar": {"aircraftAsTarget": True}, "irst": {}},
                                                           {"r": ("radar", ""), "s": ("", "searchRadar"), "i": ("irst", "irst")})})
        rad = lambda key, r: air("air", unit(), wc, sy={"se": [[key, "radar", {"k": "radar", "r": r, "ro": "st"}]]})[0].get("rad")
        self.assertEqual(rad("ps_37a", 100000), 70)  # JA37: its sea search reaches further than its air search
        self.assertIsNone(rad("ari_5390", 278000))  # Buccaneer: a radar for ships and ground only
        self.assertEqual(rad("ps_011", 30000), 30)

    def test_vne(self):
        self.assertEqual(air("air", unit(), Files(), lim={"v": 870})[0]["vne"], 870)
        lim = {"v": 1300, "m": 2.0, "sw": [[0, 900, 0.9], [1, 1300, 2.0]]}  # variable sweep: v is already the swept-back limit
        self.assertEqual(air("air", unit(), Files(), lim=lim)[0]["vne"], 1300)
        self.assertNotIn("vne", air("heli", unit(), Files(), lim={"v": 350})[0])

    def test_heli_thermal(self):
        # night_vision gives {role: [kind, generation]}: s the targeting sight, g the gunner
        s, su = air("heli", unit(), Files(), sy={"nv": {"s": ["t", 2], "p": ["ir", 1]}, "su": {"nv": {"p": ["ir", 1]}}})
        self.assertEqual((s["th"], su["th"]), (1, 0))
        self.assertEqual(air("heli", unit(), Files(), sy={"nv": {"g": ["t", 3]}})[0]["th"], 1)
        self.assertNotIn("th", air("heli", unit(), Files(), sy={"nv": {"s": ["ir", 2], "p": ["t", 1]}})[0])
        self.assertNotIn("th", air("air", unit(), Files(), sy={"nv": {"s": ["t", 2]}})[0])  # aircraft: no such duel stat


class Naval(unittest.TestCase):
    def test_naval_primary_battery(self):
        wc = Files(**{"main.blk": gun(0.2, 25), "aa.blk": gun(7.5, 0.12)})
        u = unit([weapon("gunner0", "main.blk", triggerGroup="primary"), weapon("gunner1", "main.blk", triggerGroup="primary"),
                  weapon("gunner2", "aa.blk", triggerGroup="machinegun")])
        s, su = duelstats.naval_stats(u, wc, {"se": [["sg", "radar", {"k": "radar", "r": 30000, "ro": "s"}]]})
        self.assertEqual((s["fm"], s["rad"], su), (600.0, 30, {}))
        self.assertEqual(duelstats.naval_stats(unit([weapon("gunner0", "aa.blk", triggerGroup="machinegun")]), wc, {}), ({"fa": 54}, {}))

    def test_all_guns_firepower(self):
        # PGM-9: one 76 mm in its primary group, two twin 40 mm Bofors in its secondary one; a brawl uses them all
        wc = Files(**{"76mm.blk": gun(0.8, 5.9), "40mm.blk": gun(2, 0.9)})
        u = unit([weapon("gunner0", "76mm.blk", triggerGroup="primary")] + [weapon("gunner1", "40mm.blk", triggerGroup="secondary")] * 4)
        s, su = duelstats.naval_stats(u, wc, {})
        self.assertEqual((s["fm"], s["fa"], su), (283, 715, {}))

    def test_caliber_of_the_primary_group(self):
        # R-130: its first ammo group and largest gun a 37 mm, its primary group (the guns fm counts) two 20 mm
        cal = {"37mm.blk": 37.0, "20mm.blk": 20.0}.get  # a launcher has none
        r130 = unit([weapon("gunner0", "37mm.blk", triggerGroup="secondary"), weapon("gunner1", "20mm.blk", triggerGroup="primary"),
                     weapon("gunner2", "20mm.blk", triggerGroup="primary"), weapon("gunner3", "rockets.blk", triggerGroup="primary")])
        with mock.patch.object(builder, "_caliber_mm", cal):
            self.assertEqual(builder.vehicle_stats("boat", r130, {}, {}, {}, [{"p": "37mm.blk"}])["cal"], 20.0)
            no_primary = unit([weapon("gunner0", "37mm.blk", triggerGroup="secondary")])
            self.assertEqual(builder.vehicle_stats("boat", no_primary, {}, {}, {}, [{"p": "37mm.blk"}])["cal"], 37.0)  # its first ammo group's

    def test_free_requirement_is_stock(self):
        # every torpedo preset needs ship_torpedoes, a hidden modification each vessel has from the start
        torpedoes = {"id": "torpedoes", "w": [["mark15", 10]], "req": "ship_torpedoes"}
        self.assertTrue(duelstats.preset_is_stock(torpedoes, {}, {"ship_torpedoes": {"tier": 0, "value": 0, "costGold": 0}}))
        self.assertFalse(duelstats.preset_is_stock(torpedoes, {}, {"ship_torpedoes": {"tier": 0, "value": 91}}))
        self.assertFalse(duelstats.preset_is_stock(torpedoes, {}, {}))  # not in the vehicle's table
        free = {"ship_torpedoes": {"tier": 0}, "ship_mines": {"tier": 2}}
        tubes = {"WeaponSlots": {"WeaponSlot": [{"index": 1, "WeaponPreset": [{"name": "tubes", "reqModification": "ship_torpedoes"}]}]}}
        self.assertTrue(duelstats.preset_is_stock({"id": "p", "w": [], "s": {"1": "tubes"}}, tubes, free))  # a slot preset's
        self.assertFalse(duelstats.preset_is_stock({"id": "p", "w": [], "req": ["ship_torpedoes", "ship_mines"]}, {}, free))

    def test_stock_speed(self):
        # three seakeeping modifications slow a vessel while they are not researched (invertEnableLogic)
        slow = {"new_ship_hull": 0.97, "new_ship_screw": 0.95, "new_ship_engine": 0.93}
        table = {m: {"invertEnableLogic": True, "effects": {"mulMaxSpeed": x, "mulMaxReverseSpeed": x}} for m, x in slow.items()}
        with mock.patch.object(builder, "_GLOBAL_MODS", table):
            f = builder.stock_factors({"modifications": {m: {} for m in slow}}, set(slow))
        self.assertEqual(builder.stock_stats("ship", {"spd": 65, "fm": 2700}, f), {"spd": 56})  # Fletcher, as its wiki card
        self.assertEqual(builder.stock_stats("boat", {"spd": 94}, f), {"spd": 81})  # G-5

    def test_modification_replaces_the_battery(self):
        # Flagstaff: a modification swaps the 152 mm for a 40 mm Bofors that throws more a minute
        wc = Files(**{"152mm.blk": gun(0.1, 18), "40mm.blk": gun(2, 1.2)})
        u = {**unit([weapon("gunner0", "152mm.blk", triggerGroup="primary")]),
             "modifications": {"bofors": {"effects": {"commonWeapons": {"Weapon": [weapon("gunner0", "40mm.blk", triggerGroup="primary")]}}}}}
        self.assertEqual(duelstats.naval_stats(u, wc, {}, {"bofors"}), ({"fm": 144, "fa": 144}, {"fm": 108, "fa": 108}))
        u["commonWeapons"] = {"Weapon": [weapon("gunner0", "40mm.blk", triggerGroup="machinegun")]}
        # fm is measured, not a capability: a stock boat without a main battery has it unknown, not 0
        self.assertEqual(duelstats.naval_stats(u, wc, {}, {"bofors"}), ({"fm": 144, "fa": 144}, {"fm": None}))


class Catalog(unittest.TestCase):
    def test_container_mass(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dm, data = Path(tmp.name) / "dm", Path(tmp.name) / "data"
        weapons = dm / "aces.vromfs.bin_u" / "gamedata" / "weapons"
        files = {"rocketguns/ffar.blkx": {"rocket": {"mass": 6.2}},
                 "rocketguns/aim_9.blkx": {"rocket": {"mass": 85.0, "bulletType": "aam", "guidanceType": "ir"}},
                 "containers/ffar_pod.blkx": {"container": True, "blk": "gameData/Weapons/rocketGuns/ffar.blk", "bullets": 19, "mass": 40.0},
                 "containers/aim_9_rail.blkx": {"container": True, "blk": "gameData/Weapons/rocketGuns/aim_9.blk", "bullets": 2}}
        for rel, d in files.items():
            (weapons / rel).parent.mkdir(parents=True, exist_ok=True)
            (weapons / rel).write_text(json.dumps(d), encoding="utf-8")
        data.mkdir()
        with mock.patch.object(builder, "DM", dm), mock.patch.object(builder, "DATA", data), mock.patch.object(builder, "log"):
            catalog = builder.build_weapon_catalog(builder.WeaponCache(builder.Lang()))
        self.assertEqual((catalog["ffar_pod"]["m"], catalog["ffar_pod"]["pod"]), (157.8, 19))  # its own 40 kg and 19 rockets
        self.assertEqual(catalog["aim_9_rail"]["m"], 170)  # a container without a mass of its own


class Wiring(unittest.TestCase):
    def test_build_vehicles_writes_the_stats(self):
        """build_vehicles: air_stats for aircraft and helicopters (with the modifications and the dive limit), spaa_stats
        for SPAA and naval_stats for ships (with the modifications), the stock values in su, the stock preset ids for
        guided_stats."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dm, data, gd = Path(tmp.name) / "dm", Path(tmp.name) / "data", "aces.vromfs.bin_u/gamedata/"
        ns23 = "gameData/Weapons/ns23.blk"
        files = {
            "char.vromfs.bin_u/config/wpcost.blkx": {
                "t_plane": {"unitMoveType": "air", "unitClass": "exp_fighter", "modifications": {"gun_pods": {"tier": 1}, "n37": {"tier": 2}}},
                "t_heli": {"unitMoveType": "helicopter", "unitClass": "exp_helicopter", "modifications": {"free_pods": {"tier": 0}}},
                "t_spaa": {"unitMoveType": "tank", "unitClass": "exp_SPAA", "modifications": {"guns": {"tier": 1}}},
                "t_ship": {"unitMoveType": "ship", "unitClass": "exp_destroyer",
                           "modifications": {"bofors": {"tier": 1}, "ship_torpedoes": {"tier": 0, "value": 0, "costGold": 0},
                                             "ship_mines": {"tier": 2}}}},
            gd + "flightmodels/t_plane.blkx": {
                "commonWeapons": {"Weapon": [weapon("cannon", ns23)]},
                "weapon_presets": {"preset": [{"name": "default", "blk": "gameData/FlightModels/weaponPresets/t_default.blk"},
                                              {"name": "pods", "blk": "gameData/FlightModels/weaponPresets/t_pods.blk", "reqModification": "gun_pods"}]},
                "modifications": {"n37": {"effects": {"commonWeapons": {"Weapon": [weapon("cannon", "gameData/Weapons/n37.blk")]}}}}},
            gd + "flightmodels/fm/t_plane.blkx": {"Vne": 870},
            gd + "flightmodels/weaponpresets/t_default.blkx": {},
            gd + "flightmodels/weaponpresets/t_pods.blkx": {"Weapon": [weapon("additional gun", ns23, external=True)]},
            gd + "flightmodels/t_heli.blkx": {"commonWeapons": {"Weapon": [weapon("gunner0", ns23)]}, "weapon_presets": {"preset": [
                {"name": "pods", "blk": "gameData/FlightModels/weaponPresets/t_heli_pods.blk", "reqModification": "free_pods"}]}},
            gd + "flightmodels/weaponpresets/t_heli_pods.blkx": {"Weapon": [weapon("additional gun", ns23, external=True)]},
            gd + "units/tankmodels/t_spaa.blkx": {"commonWeapons": {"Weapon": [weapon("gunner0", ns23)] * 2},
                                                   "modifications": {"guns": {"effects": {"commonWeapons": {"Weapon": [weapon("gunner0", ns23)] * 3}}}}},
            gd + "units/ships/t_ship.blkx": {
                "commonWeapons": {"Weapon": [weapon("gunner0", "gameData/Weapons/152mm.blk", triggerGroup="primary")]},
                "weapon_presets": {"preset": [{"name": "torpedoes", "reqModification": "ship_torpedoes"},
                                              {"name": "mines", "reqModification": "ship_mines"}, {"name": "t_ship_default"}]},
                "modifications": {"bofors": {"effects": {"commonWeapons": {
                    "Weapon": [weapon("gunner0", "gameData/Weapons/40mm.blk", triggerGroup="primary")]}}}}},
            gd + "weapons/ns23.blkx": gun(10, 0.2), gd + "weapons/n37.blkx": gun(7, 0.7),
            gd + "weapons/152mm.blkx": gun(0.1, 18), gd + "weapons/40mm.blkx": gun(2, 1.2)}
        for rel, d in files.items():
            (dm / rel).parent.mkdir(parents=True, exist_ok=True)
            (dm / rel).write_text(json.dumps(d), encoding="utf-8")
        data.mkdir()
        with mock.patch.object(builder, "DM", dm), mock.patch.object(builder, "DATA", data), \
                mock.patch.object(builder, "_GLOBAL_MODS", {}), mock.patch.object(builder, "log"):
            vehicles, details = builder.build_vehicles(builder.Lang(), None)
        v = {r["id"]: r for r in vehicles}
        plane = v["t_plane"]
        # upgraded: the N-37 and the pods' preset; stock: the NS-23 and the default preset
        self.assertEqual((plane["s"]["fg"], plane["su"]["fg"], plane["s"]["vne"]), (6.9, 2.0, 870))
        self.assertEqual(details["t_plane"]["_sp"], ["default"])
        # its chin gun and a gun pod whose preset needs a free modification: stock too
        self.assertEqual((v["t_heli"]["s"]["fg"], "fg" in v["t_heli"].get("su", {})), (4.0, False))
        self.assertEqual(details["t_ship"]["_sp"], ["torpedoes", "t_ship_default"])  # ship_torpedoes is free, ship_mines not
        self.assertEqual((v["t_spaa"]["s"]["aab"], v["t_spaa"]["su"]["aab"]), (6.0, 4.0))  # a modification adds a barrel
        self.assertEqual((v["t_ship"]["s"]["fm"], v["t_ship"]["su"]["fm"]), (144, 108))  # the Flagstaff's Bofors


class Helicopter(unittest.TestCase):
    CATALOG = {"hot": {"c": "atgm", "m": 23}, "ffar": {"c": "rockets", "m": 6.2}, "fab_250": {"c": "bombs", "m": 250}}

    def test_flexible_forward_guns(self):
        # UH-1C XM-30: an XM140 on each of triggers gunner1 and gunner2, forward mounts (no helicopter has door guns)
        wc = Files(**{"xm140.blk": gun(7, 0.4)})
        u = unit([weapon("gunner1", "xm140.blk"), weapon("gunner2", "xm140.blk")])
        self.assertEqual(air("heli", u, wc)[0]["fg"], 5.6)
        self.assertNotIn("fg", air("air", u, wc)[0])  # an aircraft's gunners man its turrets

    def test_rockets_and_bombs(self):
        # rkt: the unguided rockets and bombs of its heaviest preset, kg; pay counts its guided missiles too
        wc = Files(**{"p_hot.blk": {"Weapon": [weapon("atgm", "hot.blk", bullets=6)]},
                      "p_pod.blk": {"Weapon": [weapon("rockets", "ffar.blk", bullets=6)]},
                      "p_bombs.blk": {"Weapon": [weapon("bombs", "fab_250.blk", bullets=2), weapon("atgm", "hot.blk", bullets=4)]}})
        u = unit((), [("hot", "p_hot.blk"), ("pod", "p_pod.blk"), ("bombs", "p_bombs.blk")])
        presets = [{"id": "hot", "w": []}, {"id": "pod", "w": []}, {"id": "bombs", "w": [], "req": "bombs"}]
        s, su = air("heli", u, wc, presets, self.CATALOG)
        self.assertEqual((s["pay"], s["rkt"], su["pay"], su["rkt"]), (592, 500, 138, 37.2))  # stock: no bombs
        self.assertNotIn("rkt", air("air", u, wc, presets, self.CATALOG)[0])  # helicopters only
        s, su = air("heli", unit((), [("hot", "p_hot.blk")]), wc, presets[:1], self.CATALOG)
        self.assertEqual((s["pay"], "rkt" in s, su), (138, False, {}))  # HKP3C, Scout: anti-tank missiles only


class PresetCounts(unittest.TestCase):
    def test_torpedo_tube_on_a_gunner_counts_its_torpedoes(self):
        # L'Intrepide: one gunner1 tube of 7 torpedoes; a gun on those triggers counts its barrels, not its rounds
        files = {"tube.blk": {"torpedo": {"mass": 1000}}, "mg.blk": {"bullet": [{"caliber": 0.0127}]}}

        class Cache:
            def get(self, blk):
                return files.get(blk)

            def weapon_name(self, blk):
                return blk.split(".")[0]

        weapons = {"Weapon": [{"blk": "tube.blk", "trigger": "gunner1", "bullets": 7},
                              {"blk": "mg.blk", "trigger": "gunner1", "bullets": 500}]}
        with mock.patch.object(builder, "load", return_value=weapons):
            self.assertEqual(sorted(builder.preset_composition({"blk": "p.blk"}, None, Cache())), [["mg", 1], ["tube", 7]])


if __name__ == "__main__":
    unittest.main()
