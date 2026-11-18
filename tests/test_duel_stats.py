"""Stats the Best vehicles duels read, derived by the builder (wtftd/duelstats.py) from made-up details: a ground
vehicle's main gun and fire control, what a stock vehicle has, and the kin / heat card values."""
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from wtftd import builder, duelstats

GUN = "gameData/Weapons/groundModels_weapons/test_user_cannon.blk"
RENAMED = {"76mm_AP_1942": {"effects": {"additiveBulletMod": "76mm_ussr_AP_1942"}}, "he": {"effects": {"mulX": 1.0}}}


def shell(t: str, pc: list | None = None, v: float | None = None, mod: str = "", x: bool = False) -> dict:
    """One ammo option of a gun (vehicle_ammo): id "" is the default set; x: not normally available on the vehicle."""
    s = {k: val for k, val in (("pc", pc), ("v", v)) if val is not None}
    return {"id": mod, "t": [t], "s": s, **({"x": 1} if x else {})}


def main_gun(*opts, sf: float = 0.15) -> dict:
    return {"trig": "gunner0", "wi": 1, "sf": sf, "opts": list(opts)}


def flat(mm: float) -> list:
    return [[10, mm], [4000, mm]]  # a shaped charge's or a missile's penetration: the same at any distance


def from_file(gun: dict, *opts, mods: dict | None = None) -> tuple[dict, dict]:
    """ground_stats of a main gun whose file (its group's p) holds gun: every round of each set."""
    wc = mock.Mock(get=mock.Mock(return_value=gun))
    out = duelstats.ground_stats([{**main_gun(*opts), "p": GUN}], {}, mods or {}, wc)
    wc.get.assert_called_once_with(GUN)
    return out


class GroundStats(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(builder, "_GLOBAL_MODS", {})  # no shared modification table: no game file read
        patch.start()
        self.addCleanup(patch.stop)

    def test_pen_interpolates_and_skips_x(self):
        am = [main_gun(shell("apcbc_tank", [[10, 200], [500, 180], [1000, 160], [2000, 120]], v=792),
                       shell("apcr_tank", flat(400), v=1030, mod="apcr", x=True))]
        s, _ = duelstats.ground_stats(am, {}, {}, None)
        self.assertEqual((s["pen"], s["vel"]), ([180, 160, 120], 792))

    def test_pen_heat_and_gun_atgm_are_flat(self):
        launcher = {"trig": "gunner2", "wi": 3, "opts": [shell("atgm_tank", flat(900), mod="9m113")]}  # in atg, not pen
        am = [main_gun(shell("heat_fs_tank", flat(300)), shell("atgm_tank", flat(650), mod="atgm")), launcher]
        s, _ = duelstats.ground_stats(am, {}, {}, None)
        self.assertEqual(s["pen"], [650, 650, 650])

    def test_vel_is_fastest_unguided_shell(self):
        # Type 61: its HEAT-FS outruns its APBC; a smoke shell, however fast, hits nothing
        am = [main_gun(shell("apbc_usa_tank", flat(200), v=914), shell("heat_fs_tank", flat(300), v=1216, mod="heat"),
                       shell("he_frag_tank", flat(20), v=823, mod="he"), shell("smoke_tank", v=1300, mod="smoke"))]
        s, _ = duelstats.ground_stats(am, {}, {}, None)
        self.assertEqual(s["vel"], 1216)
        for t in ("practice_tank", "football_kick"):  # nor the others that hit nothing: the M551 football copies' kick
            self.assertNotIn("vel", duelstats.ground_stats([main_gun(shell(t, v=1500))], {}, {}, None)[0])

    def test_vel_apfsds_over_he(self):
        am = [main_gun(shell("he_frag_fs_tank", flat(42), v=850),
                       shell("apds_fs_long_tank", [[10, 600], [2000, 560]], v=1650, mod="apfsds"))]
        s, _ = duelstats.ground_stats(am, {}, {}, None)
        self.assertEqual(s["vel"], 1650)

    def test_vel_heat_only_recoilless_rifle(self):
        # M50 Ontos, Type 60 SPRG: HEAT and HESH, no kinetic shell; stock, the HEAT
        am = [main_gun(shell("heat_grenade_tank", flat(433), v=502.92),
                       shell("hesh_tank", flat(127), v=498.348, mod="hesh"))]
        s, su = duelstats.ground_stats(am, {}, {}, None)
        self.assertEqual(s["vel"], 503)
        self.assertNotIn("vel", su)

    def test_vel_never_from_a_guided_missile(self):
        # a gun-launched ATGM given a speed (the game files give none) faster than the gun's HEAT, as on the M551; a SAM
        # launcher whose missiles have one (Osa)
        am = [main_gun(shell("heat_tank", flat(380), v=682), shell("atgm_tank", flat(431), v=1000, mod="atgm"))]
        self.assertEqual(duelstats.ground_stats(am, {}, {}, None)[0]["vel"], 682)
        for t in ("atgm_tank", "sam_tank"):
            self.assertNotIn("vel", duelstats.ground_stats([main_gun(shell(t, v=580))], {}, {}, None)[0])

    def test_vel_rocket_rounds_top_speed(self):
        # AMX-30 ACRA: a guided missile by default and an HE rocket, 550 m/s at launch and 700 at most; Panzerwerfer 42:
        # rail rockets, an end speed only. A rocket's flight is in its "rocket" block, so an option's s has no v
        acra = {"bullet": {"bulletType": "atgm_tank",
                           "rocket": {"guidanceType": "saclos", "startSpeed": 150, "endSpeed": 500}},
                "142mm_fr_HE": {"bullet": {"bulletType": "he_frag_tank",
                                           "rocket": {"startSpeed": 550, "maxSpeed": 700, "endSpeed": 700}}}}
        missile, he = shell("atgm_tank", flat(660)), shell("he_frag_tank", flat(40), mod="142mm_fr_HE")
        s, su = from_file(acra, missile, he, mods={"142mm_fr_HE": {"tier": 0, "value": 0, "costGold": 0}})
        self.assertEqual(s["vel"], 700)  # the game's bullet card: maxSpeed, else endSpeed
        self.assertNotIn("vel", su)
        self.assertNotIn("vel", from_file(acra, missile)[0])  # the guided missile alone
        werfer = {"bullet": {"bulletType": "rocket_tank", "rocket": {"startSpeed": 0, "endSpeed": 340}}}
        self.assertEqual(from_file(werfer, shell("rocket_tank", flat(60)))[0]["vel"], 340)

    def test_vel_belt_fastest_round(self):
        # M15: its stock belt holds the M59A1 AP (625 m/s) first and the M54 HE (792); a belt of HE alone is researched
        gun = {"bullet": [{"bulletType": "apc_t", "speed": 624.84}, {"bulletType": "he_frag_i_t", "speed": 792.0}],
               "37mm_usa_m54_HE": {"bullet": {"bulletType": "he_frag_i_t", "speed": 792.0}}}
        belt, he = shell("apc_t", flat(50), v=624.84), shell("he_frag_i_t", flat(5), v=792, mod="37mm_usa_m54_HE")
        mods = {"37mm_usa_m54_HE": {"tier": 0, "value": 4, "reqModification": "37mm_usa_m54_HE_ammo_pack"}}
        s, su = from_file(gun, belt, he, mods=mods)
        self.assertEqual(s["vel"], 792)
        self.assertNotIn("vel", su)  # the stock belt's HE: as fast

    def test_fire_control(self):
        sy = {"el": [-8, 20], "stab": [1, 1, 30], "rf": "laser", "nv": {"g": ["t", 2]}}  # nv: [kind, generation]
        s, _ = duelstats.ground_stats([], sy, {}, None)
        self.assertEqual((s["dep"], s["stab"], s["rf"], s["th"]), (8, 2, 2, 1))
        s, _ = duelstats.ground_stats([], {"stab": [1, 0, 0], "rf": "optic", "nv": {"g": ["ir", 2], "c": ["t", 2]}}, {}, None)
        self.assertEqual((s["stab"], s["rf"]), (1, 1))
        self.assertNotIn("th", s)  # the commander's thermal is not the gunner's

    def test_depression(self):
        # the main gun's pitch limit with one decimal (T-90A 4.5), never below 0 (BM-13N: its rails rise 7 degrees at least)
        def unit(pitch):
            return {"commonWeapons": {"Weapon": {"trigger": "gunner0", "blk": "gun.blk", "limits": {"pitch": pitch}}}}
        for pitch, el, dep in (([-4.5, 14.3], "[-4.5, 14.3]", 4.5), ([7.0, 40.0], "[7.0, 40.0]", 0),
                               ([-0.0, 0.0], "[0.0, 0.0]", None)):  # the Striker's fixed launcher: no "-0" in the
            with mock.patch.dict(builder._SMOKE, {"gun.blk": False}):  # compare dialog, no depression (its missile steers)
                sy = builder.vehicle_systems("ground", unit(pitch), ())
            self.assertEqual((str(sy["el"]), duelstats.ground_stats([], sy, {}, None)[0].get("dep")), (el, dep))

    def test_stock_values(self):
        am = [main_gun(shell("apcbc_tank", flat(150)),
                       shell("he_frag_tank", flat(160), mod="he"),  # free: tier 0, no cost, nothing needed first
                       shell("apds_tank", flat(250), mod="apds"))]  # researched with its ammo pack
        mods = {"he": {"tier": 0, "value": 0, "costGold": 0},
                "apds": {"tier": 0, "value": 120, "costGold": 0, "reqModification": "apds_ammo_pack"}}
        sy = {"el": [-8, 20], "rf": "laser", "stab": [1, 1, 30], "su": {"rf": None, "stab": None}}
        s, su = duelstats.ground_stats(am, sy, mods, None)
        self.assertEqual((s["pen"], su["pen"]), ([250, 250, 250], [160, 160, 160]))
        self.assertEqual((su["rf"], su["stab"]), (0, 0))
        self.assertNotIn("dep", su)  # the same stock and upgraded
        self.assertTrue(duelstats.stock_shell("", mods))
        self.assertTrue(duelstats.stock_shell("he", mods))
        self.assertFalse(duelstats.stock_shell("apds", mods))
        self.assertFalse(duelstats.stock_shell("not_on_this_vehicle", mods))

    def test_stock_set_a_modification_gives(self):
        # T-34 (1941)'s 76mm_ussr_AP_1942 (BR-350SP, 87 mm) comes with its modification 76mm_AP_1942: stock when that one is
        am = [main_gun(shell("apbc_tank", flat(70)), shell("apbc_tank", flat(87), mod="76mm_ussr_AP_1942"))]
        free, researched = {"tier": 0, "value": 0}, {"value": 17, "reqModification": "76mm_AP_1942_ammo_pack"}
        with mock.patch.object(builder, "_GLOBAL_MODS", RENAMED):
            sus = [duelstats.ground_stats(am, {}, {"76mm_AP_1942": m}, None)[1] for m in (free, researched)]
        self.assertEqual(sus, [{}, {"pen": [70, 70, 70]}])

    def test_stock_without_any_penetrating_shell(self):
        # Vickers Mk.VI AA: its stock belt of ball rounds has no penetration figure, the AP belt is researched
        am = [main_gun(shell("ball", v=847), shell("ap_ball", [[10, 13], [1000, 3], [1600, 0]], v=783, mod="ap"))]
        s, su = duelstats.ground_stats(am, {}, {"ap": {"tier": 0, "value": 18, "reqModification": "ap_ammo_pack"}}, None)
        self.assertIsNone(su["pen"])  # a measured stat a stock vehicle lacks: unknown, not 0
        self.assertEqual(s["vel"], 847)
        self.assertNotIn("vel", su)  # the ball belt is the fastest, stock and upgraded

    def test_stock_vel_unknown_without_an_unguided_shell(self):
        # stock rounds: a gun-launched missile only; the HEAT shell is researched
        am = [main_gun(shell("atgm_tank", flat(500)), shell("heat_tank", flat(380), v=682, mod="heat"))]
        s, su = duelstats.ground_stats(am, {}, {"heat": {"tier": 0, "value": 50, "reqModification": "heat_ammo_pack"}}, None)
        self.assertEqual((s["vel"], su["vel"]), (682, None))

    def test_stock_without_a_kinetic_shell(self):
        # T-72B (1989): stock HEAT-FS and HE; the APFSDS, the ATGM and the laser rangefinder are researched
        am = [main_gun(shell("heat_fs_tank", flat(550), v=905), shell("he_frag_fs_tank", flat(42), v=850, mod="he"),
                       shell("apds_fs_tank", [[10, 457], [2000, 406]], v=1700, mod="apfsds"),
                       shell("atgm_tank", flat(700), mod="atgm"))]
        mods = {"he": {"tier": 0, "value": 0, "costGold": 0},
                "apfsds": {"tier": 0, "value": 240, "reqModification": "apfsds_ammo_pack"},
                "atgm": {"tier": 0, "value": 195, "reqModification": "atgm_ammo_pack"}}
        s, su = duelstats.ground_stats(am, {"rf": "laser", "su": {"rf": None}}, mods, None)
        self.assertEqual((s["vel"], s["pen"]), (1700, [700, 700, 700]))
        self.assertEqual(su, {"vel": 905, "pen": [550, 550, 550], "rf": 0})  # vel: its HEAT-FS; rf, a capability: 0

    def test_autocannon_flag(self):
        s, _ = duelstats.ground_stats([main_gun(shell("ap_t", flat(60)), sf=3.3)], {}, {}, None)
        self.assertEqual(s.get("auto"), 1)
        s, _ = duelstats.ground_stats([main_gun(shell("apcbc_tank", flat(150)), sf=0.15)], {}, {}, None)
        self.assertNotIn("auto", s)
        # one barrel's rate: OTOMATIC and 2S38 2 shots a second, the Raketenautomat's 2.5 rockets (its rel 0.4 s a per-shot
        # time); not the M50 Ontos's 6 rifles fired in turn at 2 a second, nor a Panzerwerfer 42's 10 tubes (their rel is a
        # full reload), nor a guided missile launcher (gl)
        for opt, sf, tubes, auto in ((shell("apds_fs_long_tank", flat(300)), 2.0, None, 1),
                                     (shell("heat_grenade_tank", flat(300)), 2.5, None, 1),
                                     (shell("heat_grenade_tank", flat(433)), 2.0, 6, None),
                                     (shell("rocket_tank", flat(60)), 2.0, 10, None),
                                     (shell("atgm_tank", flat(800)), 2.0, None, None)):
            gun = {**main_gun(opt, sf=sf), **({"tubes": tubes} if tubes else {})}
            self.assertEqual(duelstats.ground_stats([gun], {}, {}, None)[0].get("auto"), auto, (opt["t"], sf, tubes))

    def test_guided_launcher_flag(self):
        # gl, internal as auto: every round the main group normally has is a guided missile (an SS.11 carrier, a Tor-M1)
        for t in ("atgm_tank", "sam_tank"):
            s, su = duelstats.ground_stats([main_gun(shell(t, flat(600)), shell("he_frag_tank", flat(20), mod="he", x=True))],
                                           {}, {}, None)
            self.assertEqual(s.get("gl"), 1, t)
        # a gun-launched missile beside the gun's shells; no main gun
        am = [main_gun(shell("heat_tank", flat(380)), shell("atgm_tank", flat(431), mod="atgm"))]
        self.assertNotIn("gl", duelstats.ground_stats(am, {}, {}, None)[0])
        self.assertNotIn("gl", duelstats.ground_stats([], {}, {}, None)[0])
        # a missile carrier in stock too, whose only missile set is researched: no su.gl
        s, su = duelstats.ground_stats([main_gun(shell("atgm_tank", flat(600), mod="atgm"))], {}, {"atgm": {"value": 50}}, None)
        self.assertEqual((s.get("gl"), su), (1, {"pen": None}))

    def test_ground_search_radar(self):
        sy = {"se": [["sr", "radar", {"k": "radar", "ro": "s", "r": 18000}],
                     ["tr", "radar", {"k": "radar_irst", "ro": "t", "r": 30000}],  # tracking only
                     ["esm", "radar", {"k": "esm", "ro": "st", "r": 50000}], ["rwr", "rwr", {}]],
              "su": {"se": None}}
        s, su = duelstats.ground_stats([], sy, {}, None)
        self.assertEqual((s["rad"], su["rad"]), (18, 0))


class Guns:
    """What vehicle_ammo reads of the weapon files: {gun file: its ammo sets}, "" the default set."""
    lang = types.SimpleNamespace(put=lambda *a, **k: None)

    def __init__(self, sets: dict):
        self.sets = sets

    def get(self, blk):
        return {}

    def weapon_name(self, blk):
        return blk

    def bullet_sets(self, blk):
        ids = self.sets.get(blk, ())
        return ({"t": ["ap_t"]} if "" in ids else None), {i: {"t": ["ap_t"]} for i in ids if i}


class GroundAmmo(unittest.TestCase):
    def test_tubes_fired_in_turn(self):
        # M50 Ontos: one Weapon block for its 6 rifles (emitterGenRange), fired in turn; auto reads one barrel's rate
        unit = {"commonWeapons": {"Weapon": [
            {"trigger": "gunner0", "blk": "m40.blk", "bullets": 18, "emitterGenRange": [1, 6]},
            {"trigger": "gunner1", "blk": "mg.blk", "bullets": 1000, "emitterGenRange": [1, 1]}]}}
        groups = builder.vehicle_ammo(unit, "ground", set(), Guns({"m40.blk": [""], "mg.blk": [""]}))
        self.assertEqual([(g["w"], g.get("tubes")) for g in groups], [("m40.blk", 6), ("mg.blk", None)])

    def test_set_a_modification_gives_under_another_name(self):
        # T-34 (1941): its modification 76mm_AP_1942 gives the gun's set 76mm_ussr_AP_1942 (the shared modification table's
        # effects.additiveBulletMod): normally available; the APCR set no modification of it gives is not
        unit = {"commonWeapons": {"Weapon": {"trigger": "gunner0", "blk": "f34.blk", "bullets": 77}}}
        guns = Guns({"f34.blk": ["", "76mm_ussr_AP_1942", "he", "76mm_ussr_APCR_1943"]})
        with mock.patch.object(builder, "_GLOBAL_MODS", RENAMED):
            opts = builder.vehicle_ammo(unit, "ground", builder.bullet_mods({"76mm_AP_1942", "he"}), guns)[0]["opts"]
        self.assertEqual([o["id"] for o in opts if o.get("x")], ["76mm_ussr_APCR_1943"])


class MainGun(unittest.TestCase):
    def test_without_a_gunner_or_first_weapon(self):
        # nothing is gunner0 or Weapon 1 (a dummy turret, or a launcher without an ammo set): the largest caliber, never a
        # machine gun under 15 mm
        m2, m1919 = {"trig": "gunner2", "wi": 3, "p": "m2.blk"}, {"trig": "gunner4", "wi": 5, "p": "m1919.blk"}
        launcher, autocannon = {"trig": "gunner1", "wi": 2, "p": "mgm166.blk"}, {"trig": "gunner1", "wi": 2, "p": "20mm.blk"}
        unknown = {"trig": "gunner3", "wi": 4, "p": "unknown.blk"}  # its file gives no caliber
        with mock.patch.dict(builder._CAL_CACHE, {"m2.blk": 12.7, "m1919.blk": 7.6, "mgm166.blk": 163.0, "20mm.blk": 20.0,
                                                  "unknown.blk": None}):
            self.assertIs(builder.main_gun([m2, launcher, m1919]), launcher)  # LOSAT, Type 60 ATM: not the M2 listed first
            self.assertIs(builder.main_gun([m2, autocannon]), autocannon)
            self.assertIs(builder.main_gun([m2, unknown]), unknown)  # a caliber unknown is no machine gun's
            self.assertIsNone(builder.main_gun([m2, m1919]))  # M113A1 (TOW): its launcher has no ammo set, am leaves it out
            self.assertIs(builder.main_gun([m2, {**m1919, "trig": "gunner0"}])["p"], "m1919.blk")  # the gunner's, as before
            self.assertIs(builder.main_gun([launcher, {**m2, "wi": 1}])["p"], "m2.blk")  # Weapon 1, as before

    def test_build_vehicles_main_weapon(self):
        # Type 75 MLRS: its gunner's rocket launcher has no ammo set (am leaves it out) and its M2 is no main gun, so its
        # unguided rockets stand in (pen: their blast; their speed, their caliber; no auto, the tubes fire in turn); an
        # M113A1 (TOW)'s guided launcher is guided_stats' (a missile carrier); a Shturm-S's gunner is a dummy turret: its
        # depression is its launcher's, not the first Weapon's (an M2 listed before it); a BM-8-24's caliber is its
        # rocket's, as the game's bullet card gives it, not its placeholder bullet's
        with tempfile.TemporaryDirectory() as tmp:
            dm, data = Path(tmp) / "dm", Path(tmp) / "data"
            config, game = dm / "char.vromfs.bin_u" / "config", dm / "aces.vromfs.bin_u" / "gamedata"
            guns = game / "weapons" / "groundmodels_weapons"
            for folder in (config, game / "units" / "tankmodels", guns, game / "damage_model", data):
                folder.mkdir(parents=True)
            (game / "damage_model" / "explosive.blkx").write_text(json.dumps(  # kg of explosive -> mm it pierces
                {"explosiveTypeToSplashParams": {"explosiveMassToPenetration": {"p0": [0.1, 5.0], "p1": [10.0, 60.0]}}}))
            files = {"m2": {"shotFreq": 9.6, "bullet": {"bulletType": "ap_ball", "caliber": 0.0127, "speed": 929.0}},
                     "type75": {"shotFreq": 2.5, "rocket": {"bulletType": "rocket_tank", "caliber": 0.13, "mass": 43.0,
                                                            "explosiveMass": 4.8, "endSpeed": 700.0}},
                     "tow": {"rocket": {"bulletType": "atgm_tank", "caliber": 0.127, "endSpeed": 299.0, "guidanceType": "saclos"}},
                     "9m114": {"bullet": {"bulletType": "atgm_tank", "caliber": 0.13, "cumulativeDamage": {"armorPower": 650.0}}},
                     "m8": {"bullet": {"bulletType": "rocket_tank", "caliber": 0.15,
                                       "rocket": {"bulletType": "rocket_tank", "caliber": 0.082, "endSpeed": 315.0}}}}
            for k, f in files.items():
                (guns / f"{k}.blkx").write_text(json.dumps(f))

            def gun(k, trig, **w):
                return {"trigger": trig, "blk": f"gameData/Weapons/groundModels_weapons/{k}.blk", **w}
            units = {"mlrs": [gun("type75", "gunner0", bullets=30, emitterGenRange=[1, 30]), gun("m2", "gunner1", bullets=600)],
                     "tow": [gun("tow", "gunner0", bullets=10), gun("m2", "gunner2", bullets=1000)],
                     "both": [gun("type75", "gunner0", bullets=30), gun("m2", "gunner0", bullets=600)],  # its gunner's M2 in am
                     "shturm": [gun("dummy", "gunner0", dummy=True), gun("m2", "gunner2", bullets=600, limits={"pitch": [-10.0, 60.0]}),
                                gun("9m114", "gunner1", bullets=12, limits={"pitch": [-5.0, 15.0]})],
                     "bm8": [gun("m8", "gunner0", bullets=24, emitterGenRange=[1, 24])]}
            (config / "wpcost.blkx").write_text(json.dumps({k: {"unitMoveType": "tank", "unitClass": "exp_tank_destroyer"}
                                                            for k in units}))
            for vid, weapons in units.items():
                (game / "units" / "tankmodels" / f"{vid}.blkx").write_text(json.dumps({"commonWeapons": {"Weapon": weapons}}))
            with mock.patch.object(builder, "DM", dm), mock.patch.object(builder, "DATA", data), \
                    mock.patch.dict(builder._CAL_CACHE, clear=True):
                vehicles, _ = builder.build_vehicles(builder.Lang())
        s, su = ({v["id"]: v.get(k, {}) for v in vehicles} for k in ("s", "su"))
        self.assertEqual({k: s["mlrs"].get(k) for k in ("pen", "vel", "cal", "auto", "gl")},
                         {"pen": [31, 31, 31], "vel": 700, "cal": 130.0, "auto": None, "gl": None})
        self.assertFalse({"pen", "vel", "cal"} & set(s["tow"]))
        self.assertEqual(s["both"].get("cal"), 12.7)  # only a vehicle without a main gun gets the stand-in
        self.assertEqual((s["shturm"].get("dep"), s["shturm"].get("gl"), "dep" in su["shturm"]), (5, 1, False))  # stock too
        self.assertEqual(s["bm8"].get("cal"), 82.0)


class KinHeat(unittest.TestCase):
    def test_kin_heat_fixes(self):
        am = [main_gun({"id": "", "t": ["apcbc_tank"], "s": {"k": 200}},
                       {"id": "apcr", "t": ["apcr_tank"], "s": {"k": 400}, "x": 1},
                       {"id": "heat", "t": ["heat_fs_tank"], "s": {"h": 550, "pc": flat(550)}},
                       {"id": "heat_x", "t": ["heat_tank"], "s": {"h": 900, "pc": flat(900)}, "x": 1},
                       {"id": "atgm", "t": ["atgm_tank"], "s": {"pc": flat(650)}})]
        s = builder.vehicle_stats("ground", {}, {}, {}, {}, am)
        self.assertEqual((s["kin"], s["heat"]), (200, 650))

    def test_kinetic_missile(self):
        # LOSAT's MGM-166 has no shaped charge, and it speeds up: its best figure is far (775 mm at 1000 m), not at 10 m
        am = [main_gun({"id": "losat", "t": ["atgm_ke_tank"], "s": {"pc": [[10, 70], [1000, 775], [5000, 287]]}})]
        s = builder.vehicle_stats("ground", {}, {}, {}, {}, am)
        self.assertEqual((s.get("heat"), s.get("kin")), (None, 775))


if __name__ == "__main__":
    unittest.main()
