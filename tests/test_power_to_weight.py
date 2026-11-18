"""Aircraft power and thrust to weight: the game's card counts one engine on most twins and bombers, all of them on
others, and puts some jets' thrust-to-weight in the power field and some propeller aircraft's power in the thrust one."""
import math
import unittest
from unittest import mock

from wtftd import builder


def fm(engines: int, power: float, mass: float) -> dict:
    return {"EngineType0": {"Main": {"Type": "Radial", "Power": power, "AfterburnerBoost": 1.0}},
            **{f"Engine{i}": {"Type": 0} for i in range(engines)}, "Mass": {"EmptyMass": mass}}


def kind_fm(kind: str, engines: int, main: dict, empty: float, fuel: float = 0) -> dict:
    return {"EngineType0": {"Main": {"Type": kind, **main}}, **{f"Engine{i}": {"Type": 0} for i in range(engines)},
            "Mass": {"EmptyMass": empty, "MaxFuelMass0": fuel}}


def card_stats(shop: dict, flight_model: dict, lim: dict, cat: str = "air", vid: str = "") -> dict:
    with mock.patch.object(builder, "load", return_value=flight_model):
        return builder.vehicle_stats(cat, {}, {}, {"Shop": shop}, {"lim": lim, "fm": "fm/x"}, [], vid)


class CardEngineFactor(unittest.TestCase):
    def test_one_engine_card_counts_them_all(self):
        # B-17G: 0.06 hp/kg on the card, 4 x 1170 hp x 1.149 for 24.9 t (empty, fuel, oil): x 4 is 1.11 x all four's
        self.assertEqual(builder.card_engine_factor(0.06, fm(4, 1170 * 1.149, 24885)), 4)

    def test_counted_card_no_more_than_15_percent_over_every_engine(self):
        # He 219 A-7: 0.18 on the card, nearer to one engine (1550 hp x 1.1025 for 10800 + 1925 + 160 kg: 0.133) than to
        # both; doubled, 360 hp/t would be 1.36 x both engines' 265
        f = kind_fm("Inline", 2, {"Power": 1550, "AfterburnerBoost": 1.1025}, 10800, 1925)
        f["Mass"].update(OilMass=160, Takeoff=16000)
        self.assertEqual(card_stats({"powerToWeightRatio": 0.18}, f, {"eng": 2})["pw"], 305.0)

    def test_card_that_counts_every_engine_is_kept(self):
        # Ju 52: 0.29 hp/kg on the card, 3 x 830 hp for 9.8 t
        self.assertEqual(builder.card_engine_factor(0.29, fm(3, 830, 9800)), 1)

    def test_older_flight_model_engine_and_rockets(self):
        # power on the engine itself (Bf 109 F-4 style); take-off rockets are not engines here
        f = {"Engine0": {"Main": {"Type": "Inline", "Power": 1000}}, "Engine1": {"Main": {"Type": "Inline", "Power": 1000}},
             "Engine2": {"Main": {"Type": "Rocket"}}, "Mass": {"EmptyMass": 5000}}
        self.assertEqual(builder.card_engine_factor(0.2, f), 2)

    def test_single_engine_or_unknown_power(self):
        self.assertEqual(builder.card_engine_factor(0.45, fm(1, 1170, 2783)), 1)
        self.assertEqual(builder.card_engine_factor(0.06, {"Engine0": {}, "Engine1": {}}), 1)

    def test_power_card_skips_the_take_off_test(self):
        # DB-3A: 0.12 on the card is one engine's (2 x 926 hp for 8.6 t). Both over its 15 t take-off mass give 0.123;
        # the 16 t here is made up so that both give 0.116, under the card, as if the card already counted both
        f = fm(2, 926, 8565)
        f["Mass"]["Takeoff"] = 16000
        self.assertEqual(builder.card_engine_factor(0.12, f), 2)


class JetCards(unittest.TestCase):
    def test_jet_power_ratio_is_its_thrust_to_weight(self):
        # Mystère IVA: 0.41 in the power field, a jet engine
        s = card_stats({"powerToWeightRatio": 0.41}, kind_fm("Jet", 1, {"ThrustMax": {"ThrustMax0": 3240}}, 5920, 1660),
                       {"jet": True, "eng": 1})
        self.assertEqual(s.get("tw"), 0.41)
        self.assertNotIn("pw", s)


class EngineKind(unittest.TestCase):
    def test_prop_card_thrust_field_is_power(self):
        # Fokker D.21: 0.35 in the thrust field, an inline engine: 350 hp/t
        s = card_stats({"thrustToWeightRatio": 0.35}, kind_fm("Inline", 1, {"Power": 1000}, 2800), {"eng": 1})
        self.assertEqual(s.get("pw"), 350.0)
        self.assertNotIn("tw", s)

    def test_rocket_plane_keeps_thrust(self):
        s = card_stats({"thrustToWeightRatio": 0.4}, kind_fm("Rocket", 1, {}, 1900), {"eng": 1})
        self.assertEqual(s.get("tw"), 0.4)
        self.assertNotIn("pw", s)

    def test_twin_jet_card_counts_one_engine(self):
        # Meteor F.8: 1633 kgf of static dry thrust per engine for 6.9 t, the card's 0.22 is one engine's; both
        # engines over its 8061 kg take-off mass give 0.41, so the take-off test leaves the doubling alone
        f = kind_fm("Jet", 2, {"ThrustMax": {"ThrustMax0": 1633}}, 5382.6, 1524)
        f["Mass"].update(OilMass=23.47, Takeoff=8061)
        s = card_stats({"thrustToWeightRatio": 0.22}, f, {"eng": 2, "jet": True})
        self.assertEqual(s.get("tw"), 0.44)

    def test_twin_jet_card_counts_both(self):
        # F-5A: the card's 0.46 already counts both engines
        s = card_stats({"thrustToWeightRatio": 0.46}, kind_fm("Jet", 2, {"ThrustMax": {"ThrustMax0": 1200}}, 4000, 1800),
                       {"eng": 2, "jet": True})
        self.assertEqual(s.get("tw"), 0.46)

    def test_card_reaching_every_engine_at_take_off_is_kept(self):
        # Sk 60B: 2 x 720 kgf over its 5606 kg take-off mass is 0.26, so the card's 0.3 already counts both engines
        f = kind_fm("Jet", 2, {"ThrustMax": {"ThrustMax0": 720}}, 2070, 1065)
        f["Mass"].update(OilMass=12, Takeoff=5606)
        s = card_stats({"thrustToWeightRatio": 0.3}, f, {"eng": 2, "jet": True})
        self.assertEqual(s.get("tw"), 0.3)

    def test_old_model_thrust_in_newtons(self):
        # a flight model without a ThrustMax table: Main.Thrust in newtons
        s = card_stats({"thrustToWeightRatio": 0.13}, kind_fm("Jet", 2, {"Thrust": 9319.5}, 5000), {"eng": 2, "jet": True})
        self.assertEqual(s.get("tw"), 0.26)

    def test_unlike_engines_keep_the_card(self):
        # Fireball: a radial and a jet, its card (power field) is the whole aircraft's thrust-to-weight
        f = {"EngineType0": {"Main": {"Type": "Radial", "Power": 1210, "ThrustMax": {"ThrustMax0": 2700}}},
             "EngineType1": {"Main": {"Type": "Jet", "ThrustMax": {"ThrustMax0": 735}}},
             "Engine0": {"Type": 0}, "Engine1": {"Type": 1}, "Mass": {"EmptyMass": 3850, "MaxFuelMass0": 1740}}
        s = card_stats({"powerToWeightRatio": 0.55}, f, {"eng": 2, "jet": True})
        self.assertEqual(s.get("tw"), 0.55)
        self.assertNotIn("pw", s)

    def test_helicopter_card_is_kept(self):
        # a helicopter's turboshafts are propeller engines, but its card value is a placeholder kept as the game gives it
        s = card_stats({"thrustToWeightRatio": 0.49}, kind_fm("TurboProp", 2, {"Power": 1500}, 5000), {"eng": 2}, "heli")
        self.assertEqual(s.get("tw"), 0.49)
        self.assertNotIn("pw", s)

    def test_ai_drone_card_is_kept(self):
        # every AI drone's card has the same 0.71 placeholder in the thrust field, whatever its engines
        for vid, f in (("ucav_mq_1_predator", kind_fm("Inline", 1, {"Power": 115}, 512, 457)),
                       ("uav_quadcopter", kind_fm("Jet", 4, {"ThrustMax": {"ThrustMax0": 2}}, 4))):
            with self.subTest(vid):
                s = card_stats({"thrustToWeightRatio": 0.71}, f, {}, vid=vid)
                self.assertEqual(s.get("tw"), 0.71)
                self.assertNotIn("pw", s)


class WingLoading(unittest.TestCase):
    def test_broken_card_is_unknown(self):
        # P-39Q-5: 18.26 on its card, a dropped digit (the P-39N's says 166); the lightest real card is the Po-2's 32
        self.assertNotIn("wl", card_stats({"wingLoading": 18.26}, {}, {}))
        self.assertEqual(card_stats({"wingLoading": 32}, {}, {})["wl"], 32)
        stock = builder.stock_stats("air", card_stats({"wingLoading": 18.26}, {}, {}), {**builder.stock_factors({}, ()), "M": 1.04})
        self.assertNotIn("wl", stock)


class TurnDrag(unittest.TestCase):
    # speed lost turning: the wing's induced drag, 1 / (pi x aspect ratio x Oswald efficiency), times the wing loading
    WING = {"Span": 9.2, "Areas": {"LeftIn": 7.0, "LeftMid": 6.0, "LeftOut": 5.5, "RightIn": 7.0, "RightMid": 6.0,
                                   "RightOut": 5.5, "Aileron": 0.55}, "FlapsPolar0": {"OswaldsEfficiencyNumber": 0.51}}

    def test_from_the_flight_model_wing(self):  # J-10C: 9.2 m, 37 m2, Oswald 0.51, 311 kg/m2
        fm = {**kind_fm("Inline", 1, {"Power": 900}, 2000), "Aerodynamics": {"WingPlane": self.WING}}
        s = card_stats({"powerToWeightRatio": 0.45, "wingLoading": 311}, fm, {"eng": 1})
        self.assertEqual(s["ind"], round(311 / (math.pi * 9.2 ** 2 / 37 * 0.51), 1))
        self.assertEqual(builder.stock_stats("air", s, {"P": 1.0, "M": 1.1, "D": 1.0, "Y": 1.0, "T": 1.0})["ind"],
                         round(s["ind"] * 1.1))  # heavier in stock, like the wing loading

    def test_older_flight_model(self):  # Spitfire IX: Wingspan, Areas Wing*, Aerodynamics' Oswald
        fm = {**kind_fm("Inline", 1, {"Power": 1500}, 3000), "Wingspan": 11.25, "Aerodynamics": {"OswaldsEfficiencyNumber": 0.9},
              "Areas": {"WingLeftIn": 4.146, "WingLeftMid": 3.746, "WingLeftOut": 3.346, "WingRightIn": 4.146, "WingRightMid": 3.746,
                        "WingRightOut": 3.346, "WingLeftCut": 0.15, "Aileron": 0.878}}
        s = card_stats({"powerToWeightRatio": 0.5, "wingLoading": 149}, fm, {"eng": 1})
        self.assertEqual(s["ind"], round(149 / (math.pi * 11.25 ** 2 / 22.476 * 0.9), 1))

    def test_no_wing_data_no_value(self):
        s = card_stats({"powerToWeightRatio": 0.45, "wingLoading": 311}, kind_fm("Inline", 1, {"Power": 900}, 2000), {"eng": 1})
        self.assertNotIn("ind", s)


class CardAgainstFlightModel(unittest.TestCase):
    # a propeller card more than 15% off its flight model (every engine over the lightest mass) comes within 15% of it
    def test_card_above_is_capped(self):  # BF2C-1: 540 hp/t on the card, 344 in the flight model
        s = card_stats({"powerToWeightRatio": 0.54}, kind_fm("Radial", 1, {"Power": 688}, 2000), {"eng": 1})
        self.assertEqual(s["pw"], round(344 * 1.15, 1))

    def test_card_below_is_raised(self):  # Fury Mk II: 250 against 453
        s = card_stats({"powerToWeightRatio": 0.25}, kind_fm("Inline", 1, {"Power": 906}, 2000), {"eng": 1})
        self.assertEqual(s["pw"], round(453 / 1.15, 1))

    def test_card_within_15_percent_is_kept(self):
        s = card_stats({"powerToWeightRatio": 0.4}, kind_fm("Inline", 1, {"Power": 900}, 2000), {"eng": 1})
        self.assertEqual(s["pw"], 400.0)


if __name__ == "__main__":
    unittest.main()
