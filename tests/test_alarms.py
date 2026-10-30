"""Flight limits from a flight model, aircraft recognition, alarms: no game needed (fake /state)."""
import json
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from wtftd import alarms, battle, builder, flightlog

SU30 = {"v": 1540, "m": 2.1, "gear": 700, "flaps": [[0.2, 1018], [1, 600]], "fuel": [9400, 9400], "eng": 2}
J10 = {"v": 1543, "m": 2.1, "gear": 620, "flaps": [[0.1, 550], [1, 400]], "fuel": [5945, 6220.02], "eng": 1}
PLANES = {"su_30mkk": SU30, "j_10c": J10, "j_10_twin": dict(J10, v=900), "j_10a": dict(J10)}


WORDS = alarms.labels("en")


def state(**fields) -> dict:
    return {"valid": True, "Mfuel0, kg": 5945, "IAS, km/h": 500, "M": 0.5, "throttle 1, %": 100, **fields}


def details(planes=PLANES) -> dict:
    return {vid: {"st": {"lim": lim}} for vid, lim in planes.items()}


class Limits(unittest.TestCase):
    def fm(self, **mass):
        return {"Vne": 800, "VneMach": 0.9, "Mass": {"MaxFuelMass0": 500, **mass}, "Engine0": {"Type": 0},
                "EngineType0": {"Main": {"Type": "Inline"}}}

    def test_strength_block_when_nothing_at_the_root(self):
        lim = builder.flight_limits({"Aerodynamics": {"WingPlane": {"Strength": {"VNE": 1540, "MNE": 2.1}}}}, "air")
        self.assertEqual((lim["v"], lim["m"]), (1540, 2.1))

    def test_root_wins(self):
        fm = dict(self.fm(), Aerodynamics={"WingPlane": {"Strength": {"VNE": 1, "MNE": 1}}})
        self.assertEqual(builder.flight_limits(fm, "air")["v"], 800)

    def test_variable_sweep_keeps_the_swept_limit(self):
        strength = lambda v, m: {"Strength": {"VNE": v, "MNE": m}}
        aero = {"WingPlaneSweep1": dict(strength(1555, 2.25), Sweep=1.0), "WingPlaneSweep0": dict(strength(1021, 0.96), Sweep=0.0)}
        lim = builder.flight_limits({"Aerodynamics": aero}, "air")
        self.assertEqual(lim["sw"], [[0.0, 1021, 0.96], [1.0, 1555, 2.25]])
        self.assertEqual((lim["v"], lim["m"]), (1555, 2.25))

    def test_flaps_flat_list(self):
        lim = builder.flight_limits(self.fm(FlapsDestructionIndSpeedP=[0.1, 550, 1.0, 400]), "air")
        self.assertEqual(lim["flaps"], [[0.1, 550], [1.0, 400]])

    def test_flaps_one_pair_per_key(self):
        lim = builder.flight_limits(self.fm(FlapsDestructionIndSpeedP1=[1.0, 600], FlapsDestructionIndSpeedP0=[0.2, 1018]), "air")
        self.assertEqual(lim["flaps"], [[0.2, 1018], [1.0, 600]])

    def test_flaps_repeated_key(self):  # BB-1: P1 twice
        lim = builder.flight_limits(self.fm(FlapsDestructionIndSpeedP0=[0.1, 450],
                                            FlapsDestructionIndSpeedP1=[[0.3, 340], [1.0, 280]]), "air")
        self.assertEqual(lim["flaps"], [[0.1, 450], [0.3, 340], [1.0, 280]])

    def test_flaps_lone_speed(self):  # I-16
        self.assertEqual(builder.flight_limits(self.fm(FlapsDestructionIndSpeedP=700.0), "air")["flaps"], [[0, 700.0]])

    def test_helicopter_flaps_ignored(self):
        lim = builder.flight_limits(self.fm(FlapsDestructionIndSpeedP1=[0.0, 600], GearDestructionIndSpeed=420), "heli")
        self.assertNotIn("flaps", lim)
        self.assertEqual(lim["gear"], 420)

    def test_no_gear_limit(self):
        self.assertEqual(builder.flight_limits(self.fm(), "air")["gear"], 0)

    def test_fuel_both_values_with_repeated_tanks(self):  # Il-2M: a tank key twice
        lim = builder.flight_limits(self.fm(Parts={"tank1_capacity": [235.25, 135.25], "tank2_capacity": 200, "tank2_hp": 9}), "air")
        self.assertEqual(lim["fuel"], [500, 570.5])

    def test_fm_file_spellings(self):
        want = builder.fm_file("fm/x.blk")
        self.assertEqual(want.parts[-2:], ("fm", "x.blkx"))
        for path in ("fm/x", "/fm/x.blk", "FM/X.blk"):
            self.assertEqual(builder.fm_file(path), want, path)

    def test_no_limits_no_entry(self):
        self.assertEqual(builder.flight_limits({"Mass": {}}, "air"), {})

    def test_engines_skip_take_off_rockets(self):
        fm = {"Engine0": {"Type": 0}, "Engine1": {"Type": 0}, "Engine2": {"Type": 1},
              "EngineType0": {"Main": {"Type": "Jet"}}, "EngineType1": {"Main": {"Type": "Rocket"}}}
        self.assertEqual(builder.engine_count(fm), 2)

    def test_engines_described_in_place(self):  # Me 262 C: no EngineType<n>
        fm = {"Engine0": {"Main": {"Type": "Jet"}}, "Engine1": {"Main": {"Type": "Rocket"}}}
        self.assertEqual(builder.engine_count(fm), 1)

    def test_rocket_plane_has_engines(self):  # Me 163
        fm = {"Engine0": {"Type": 0}, "EngineType0": {"Main": {"Type": "Rocket"}}}
        self.assertEqual(builder.engine_count(fm), 1)


class Speeds(unittest.TestCase):
    def test_flaps_between_points(self):
        self.assertEqual(alarms.flaps_limit([[0.2, 1000], [1, 600]], 0.6), 800)

    def test_flaps_outside_the_points(self):
        self.assertEqual(alarms.flaps_limit([[0.2, 1000], [1, 600]], 0.1), 1000)
        self.assertEqual(alarms.flaps_limit([[0.2, 1000], [0.5, 600]], 1), 600)

    def test_same_position_twice(self):  # Ki-87
        self.assertEqual(alarms.flaps_limit([[0.1, 400], [0.1, 480], [1, 280]], 0.1), 400)

    def test_airframe_is_the_worse_of_speed_and_mach(self):
        lim = {"v": 1000, "m": 1.0}
        self.assertEqual(alarms.percents(lim, {"IAS, km/h": 500, "M": 0.8})["airframe"], 80)
        self.assertEqual(alarms.percents(lim, {"IAS, km/h": 900, "M": 0.5})["airframe"], 90)

    def test_gear_and_flaps_only_when_out(self):
        self.assertEqual(set(alarms.percents(SU30, {"IAS, km/h": 300, "gear, %": 0})), {"airframe"})
        self.assertEqual(alarms.percents(SU30, {"IAS, km/h": 350, "gear, %": 100})["gear"], 50)
        self.assertEqual(alarms.percents(SU30, {"IAS, km/h": 300, "flaps, %": 100})["flaps"], 50)

    def test_no_gear_limit_no_line(self):
        self.assertNotIn("gear", alarms.percents(dict(SU30, gear=0), {"IAS, km/h": 300, "gear, %": 100}))

    def test_missing_fields(self):
        self.assertEqual(alarms.percents(J10, {"IAS, km/h": 0})["airframe"], 0)

    def test_thresholds(self):
        on = alarms.clean(None, WORDS)["alarms"]
        self.assertEqual(alarms.active({"airframe": 92.9, "gear": 89.9, "flaps": 89.9}, on), [])
        self.assertEqual(alarms.active({"airframe": 93, "gear": 90, "flaps": 90}, on), ["airframe", "gear", "flaps"])

    def test_a_switched_off_alarm_stays_off(self):
        on = alarms.clean({"alarms": {"gear": {"on": False}}}, WORDS)["alarms"]
        self.assertEqual(alarms.active({"gear": 500}, on), [])


class Recognition(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "global.blk"

    def tearDown(self):
        self.tmp.cleanup()

    def test_reported_type(self):
        self.assertEqual(alarms.reported_type({"valid": True, "army": "air", "type": "su_30mkk"}), "su_30mkk")  # in game
        self.assertIsNone(alarms.reported_type({"valid": True, "type": 3}))

    def test_saved_model(self):
        self.path.write_text('x:i=1\nselectedAir{\n  current_model:t="j_10c"\n}\n', encoding="utf-8")
        self.assertEqual(alarms.read_model(self.path), "j_10c")

    def test_file_absent(self):
        self.assertIsNone(alarms.read_model(self.path))

    def test_key_absent(self):
        self.path.write_text('selectedTank{\n  current_model:t="us_m2a4"\n}\n', encoding="utf-8")
        self.assertIsNone(alarms.read_model(self.path))

    def test_the_real_aircraft_among_look_alikes(self):
        self.assertIs(alarms.recognise(PLANES, state(), "j_10_twin"), PLANES["j_10_twin"])

    def test_either_fuel_value(self):
        self.assertIs(alarms.recognise(PLANES, state(**{"Mfuel0, kg": 6220}), "j_10c"), J10)

    def test_look_alikes_with_other_limits_are_never_guessed(self):
        for model in (None, "su_30mkk", "gone"):
            self.assertIsNone(alarms.recognise(PLANES, state(), model), model)

    def test_same_limits_any_will_do(self):
        twins = {k: PLANES[k] for k in ("j_10c", "j_10a")}
        self.assertEqual(alarms.recognise(twins, state(), None), J10)

    def test_engines_must_fit(self):
        self.assertIsNone(alarms.recognise({"j_10c": J10}, state(**{"throttle 2, %": 100}), "j_10c"))

    def test_nothing_fits(self):
        self.assertIsNone(alarms.recognise(PLANES, state(**{"Mfuel0, kg": 1}), "j_10c"))


class Watching(unittest.TestCase):
    def setUp(self):
        self.reply = json.dumps(state()).encode()
        self.indicators = b'{"valid": false}'  # the fallback's case, seen on 2.59
        self.on_map = False
        self.model = "j_10c"
        self.watch = alarms.Watch(lambda path: self.indicators if path == "/indicators" else self.reply,
                                  lambda: self.data, lambda: self.on_map, lambda: None)
        self.data = details()
        self.watch.enabled = True
        self.watch.model = lambda: self.model
        patcher = mock.patch.object(alarms, "beep")
        self.beep = patcher.start()
        self.addCleanup(patcher.stop)

    def fly(self, **fields):
        self.reply = json.dumps(state(**fields)).encode()
        return self.watch.tick()

    def texts(self):
        return [x[0] for x in self.watch.display]

    def test_lines_say_real_speeds(self):
        self.assertEqual(self.fly(**{"IAS, km/h": 771, "gear, %": 100}), alarms.POLL_S)
        self.assertEqual(self.texts(), ["IAS    771 / 1543 km/h", "MACH   0.50 / 2.10", "GEAR   771 / 620 km/h"])

    def test_only_the_line_of_the_alarm_goes_to_the_alert_colour(self):
        self.fly(**{"IAS, km/h": 771, "gear, %": 100})
        cfg = self.watch.cfg
        self.assertEqual([x[1] for x in self.watch.display], [cfg["color"], cfg["color"], cfg["alert"]])

    def test_thresholds_and_sounds_are_the_players(self):
        self.watch.set_config(alarms.clean({"alarms": {"airframe": {"at": 30, "hz": 500, "ms": 80}}}, WORDS), {})
        self.fly()
        self.beep.assert_called_once_with(500, 80)

    def test_gear_alarm_beeps_at_its_pitch(self):
        self.fly(**{"gear, %": 100, "IAS, km/h": 600})
        self.beep.assert_called_once_with(1000, alarms.BEEP_MS)

    def test_no_alarm_no_beep(self):
        self.fly()
        self.assertNotIn(self.watch.cfg["alert"], [x[1] for x in self.watch.display])
        self.beep.assert_not_called()

    def test_beeps_are_spaced(self):
        self.fly(**{"IAS, km/h": 1500})
        self.fly(**{"IAS, km/h": 1500})
        self.assertEqual(self.beep.call_count, 1)
        self.watch._last_beep -= 1
        self.fly(**{"IAS, km/h": 1500})
        self.assertEqual(self.beep.call_count, 2)

    def test_not_flying(self):
        for reply in (None, b"", b"not json", b"[]", b'{"valid": false}', b'{"valid": true}',
                      json.dumps(state(**{"IAS, km/h": 0})).encode()):
            self.watch.display = [("x", "#000000", 40)]
            self.reply = reply
            self.assertEqual(self.watch.tick(), alarms.IDLE_S, reply)
            self.assertEqual(self.watch.display, [], reply)
        self.beep.assert_not_called()

    def test_disabled(self):
        self.watch.enabled = False
        self.fly(**{"IAS, km/h": 1500})
        self.assertEqual(self.watch.display, [])
        self.beep.assert_not_called()

    def test_unknown_aircraft_beeps_once_and_stays_silent(self):
        self.model = None
        for _ in range(3):
            self.fly(**{"IAS, km/h": 1500})
        self.assertEqual(self.watch.display[0][:2], ("AIRCRAFT UNKNOWN", self.watch.cfg["alert"]))
        self.assertEqual(self.texts()[1:], ["IAS    1500 / N/A km/h", "MACH   0.50 / N/A"])  # the game's own values remain
        self.beep.assert_called_once_with(*alarms.UNKNOWN_BEEP)

    def test_changing_aircraft_in_the_hangar(self):
        self.fly()
        self.assertIs(self.watch._lim, J10)
        self.reply = b'{"valid": false}'
        self.watch.tick()
        self.model = "su_30mkk"
        self.fly(**{"Mfuel0, kg": 9400, "throttle 2, %": 100})
        self.assertIs(self.watch._lim, SU30)

    def test_new_data_after_an_update(self):
        self.fly()
        self.data = details({"j_10c": dict(J10, v=1000)})
        self.reply = None
        self.watch.tick()
        self.fly()
        self.assertEqual(self.watch._lim["v"], 1000)

    def test_swept_limit_is_said(self):
        self.data = details({"j_10c": dict(J10, sw=[[0, 1000, 1], [1, 1543, 2.1]])})
        self.fly(**{"IAS, km/h": 771})
        self.assertEqual(self.texts()[0], "IAS    771 / 1543 km/h (swept limit)")

    def test_the_game_naming_the_aircraft_comes_before_the_fallback(self):
        self.model = "su_30mkk"
        self.indicators = b'{"valid": true, "army": "air", "type": "j_10_twin"}'
        self.fly()
        self.assertIs(self.watch._lim, PLANES["j_10_twin"])

    def test_the_game_is_believed_even_if_fuel_says_otherwise(self):  # external tanks, if they change Mfuel0
        self.model = None
        self.indicators = b'{"valid": true, "type": "j_10c"}'
        self.fly(**{"Mfuel0, kg": 7000})
        self.assertIs(self.watch._lim, J10)
        self.beep.assert_not_called()

    def test_fallback_when_indicators_says_nothing_useful(self):
        for reply in (None, b"", b"not json", b"[]", b'{"valid": false}', b'{"valid": true}',
                      b'{"valid": true, "type": 3}', b'{"valid": true, "type": "wtftd_custom"}'):
            self.indicators = reply
            self.watch._key = None
            self.fly()
            self.assertIs(self.watch._lim, J10, reply)

    def test_indicators_coming_back_mid_flight(self):
        self.model = None
        self.fly()
        self.assertIsNone(self.watch._lim)
        self.indicators = b'{"valid": true, "type": "j_10c"}'
        self.fly()
        self.assertIs(self.watch._lim, J10)

    def test_generated_mission_comes_first(self):
        self.model = "su_30mkk"
        self.on_map = True
        self.indicators = b'{"valid": true, "type": "su_30mkk"}'  # a custom vehicle's host
        self.watch.mission = {"id": "j_10a", "fuel": None, "unbreakable": False}
        self.fly()
        self.assertIs(self.watch._lim, PLANES["j_10a"])

    def test_generated_mission_with_its_own_fuel(self):
        self.on_map = True
        self.watch.mission = {"id": "j_10c", "fuel": 3000.0, "unbreakable": False}
        self.fly(**{"Mfuel0, kg": 3000})
        self.assertIs(self.watch._lim, J10)

    def test_unbreakable_airframe(self):
        self.on_map = True
        self.watch.mission = {"id": "j_10c", "fuel": None, "unbreakable": True}
        self.fly(**{"IAS, km/h": 1500})
        self.assertEqual(self.texts()[0], "UNBREAKABLE AIRFRAME")
        self.assertNotIn(self.watch.cfg["alert"], [x[1] for x in self.watch.display])
        self.beep.assert_not_called()

    def test_real_battle_after_an_unbreakable_mission(self):
        self.watch.mission = {"id": "j_10c", "fuel": None, "unbreakable": True}
        self.fly(**{"IAS, km/h": 1500})  # another map: not that mission
        self.beep.assert_called_once_with(1400, alarms.BEEP_MS)

    def test_a_mission_with_another_aircraft_does_not_count(self):
        self.on_map = True
        self.watch.mission = {"id": "su_30mkk", "fuel": None, "unbreakable": True}
        self.fly(**{"IAS, km/h": 1500})
        self.assertIs(self.watch._lim, J10)
        self.assertEqual(self.beep.call_count, 1)


class Lines(unittest.TestCase):
    VALUES = {"IAS, km/h": 1284, "M": 1.25, "RPM 2": 13300.5, "vne": 1540, "swept": ""}

    def test_values_with_their_decimals(self):
        self.assertEqual(alarms.fill("IAS {ias} / {vne} km/h", self.VALUES), "IAS 1284 / 1540 km/h")
        self.assertEqual(alarms.fill("M {mach}", self.VALUES), "M 1.25")

    def test_decimals_can_be_chosen(self):
        self.assertEqual(alarms.fill("{mach:3} {ias:1}", self.VALUES), "1.250 1284.0")

    def test_any_field_of_the_game_under_its_own_name(self):
        self.assertEqual(alarms.fill("{RPM 2}", self.VALUES), "13300.5")

    def test_what_is_not_there(self):
        self.assertEqual(alarms.fill("{heading} {nothing}", self.VALUES), "N/A N/A")

    def test_plain_text_and_empty_values(self):
        self.assertEqual(alarms.fill("hello { {ias", self.VALUES), "hello { {ias")
        self.assertEqual(alarms.fill("IAS {swept}", self.VALUES), "IAS")

    def test_no_python_formatting_gets_through(self):
        self.assertEqual(alarms.fill("{ias.__class__} {ias!r}", self.VALUES), "N/A N/A")

    def test_computed_values(self):
        out = alarms.computed(SU30, {"IAS, km/h": 770, "M": 1.05, "flaps, %": 60, "gear, %": 100, "Mfuel, kg": 4700,
                                     "Mfuel0, kg": 9400}, WORDS)
        self.assertEqual((out["vne"], out["mne"], out["gear_max"]), (1540, 2.1, 700))
        for key, value in (("airframe_pct", 50), ("gear_pct", 110), ("flaps_max", 809), ("fuel_pct", 50), ("margin", 770)):
            self.assertAlmostEqual(out[key], value, msg=key)

    def test_margin_is_to_the_nearest_limit(self):  # high up: Mach comes first
        self.assertAlmostEqual(alarms.computed(SU30, {"IAS, km/h": 700, "M": 1.75}, WORDS)["margin"], 140)

    def test_unknown_aircraft_has_no_limits(self):
        self.assertEqual(alarms.computed(None, {"IAS, km/h": 700}, WORDS), {"swept": ""})

    def test_conditions(self):
        cfg = alarms.clean(None, WORDS)
        cfg["lines"] = [{"text": w, "when": w, "alarm": "", "color": "", "size": 0} for w in alarms.WHEN]
        shown = lambda values, on: [x[0] for x in alarms.lines_for(cfg, values, on)]
        self.assertEqual(shown({}, []), ["always"])
        self.assertEqual(shown({"gear, %": 1, "flaps, %": 1, "airbrake, %": 1, "rec": 1}, ["gear"]), list(alarms.WHEN))

    def test_a_line_keeps_its_own_size_and_colour(self):
        cfg = alarms.clean(None, WORDS)
        cfg["lines"] = [{"text": "x", "when": "always", "alarm": "", "color": "#123456", "size": 90}]
        self.assertEqual(alarms.lines_for(cfg, {}, []), [("x", "#123456", 90)])


class Computed(unittest.TestCase):
    def test_a_level_turn(self):  # 2 G at 100 m/s
        out = alarms.computed(None, {"TAS, km/h": 360, "Ny": 2}, WORDS)
        self.assertAlmostEqual(out["turn_radius"], 588.8, 0)
        self.assertAlmostEqual(out["turn_rate"], 9.74, 1)
        self.assertAlmostEqual(out["turn"], 37, 0)

    def test_no_turn_flying_straight(self):
        self.assertNotIn("turn", alarms.computed(None, {"TAS, km/h": 360, "Ny": 1.02}, WORDS))

    def test_horizontal_speed(self):
        self.assertAlmostEqual(alarms.computed(None, {"TAS, km/h": 360, "Vy, m/s": 60}, WORDS)["hspeed"], 288)

    def test_thrust_adds_up_and_mass_is_empty_plus_fuel(self):
        lim = dict(SU30, mass=17520)
        out = alarms.computed(lim, {"thrust 1, kgs": 1874, "thrust 2, kgs": 1874, "Mfuel, kg": 9400}, WORDS)
        self.assertEqual((out["thrust_total"], out["mass"]), (3748, 26920))
        self.assertAlmostEqual(out["twr"], 0.139, 3)

    def test_no_mass_no_ratio(self):
        self.assertNotIn("twr", alarms.computed(SU30, {"thrust 1, kgs": 1874}, WORDS))

    def test_endurance_and_range(self):
        out = alarms.computed(None, {"Mfuel, kg": 500, "TAS, km/h": 720}, WORDS, {"burn": 100})
        self.assertEqual(out["fuel_time"], "5:00")
        self.assertEqual(out["range"], 60)

    def test_nothing_burning(self):
        self.assertNotIn("fuel_time", alarms.computed(None, {"Mfuel, kg": 500}, WORDS, {"burn": 0}))

    def test_excess_power(self):
        out = alarms.computed(None, {"TAS, km/h": 360, "Vy, m/s": 10}, WORDS, {"accel": alarms.G})
        self.assertAlmostEqual(out["sep"], 110)

    def test_trend(self):
        trend = alarms.Trend()
        for t in range(0, 41, 10):  # 2 kg a second
            trend.add(t, {"Mfuel, kg": 1000 - 2 * t, "TAS, km/h": (100 + t) * 3.6})
        self.assertAlmostEqual(trend.rates()["burn"], 120)
        self.assertEqual(len(trend.points), 4)  # older than BURN_S: gone

    def test_acceleration_over_the_last_seconds(self):
        trend = alarms.Trend()
        for t, v in ((0, 100), (9, 100), (10, 120), (11, 140)):
            trend.add(t, {"TAS, km/h": v * 3.6})
        self.assertAlmostEqual(trend.rates()["accel"], 20)

    def test_a_first_reading_has_no_rates(self):
        trend = alarms.Trend()
        trend.add(0, {"Mfuel, kg": 10})
        self.assertEqual(trend.rates(), {})

    def test_refuelling_is_no_negative_burn(self):
        trend = alarms.Trend()
        trend.add(0, {"Mfuel, kg": 10})
        trend.add(10, {"Mfuel, kg": 100})
        self.assertEqual(trend.rates()["burn"], 0)

    def test_every_value_has_its_own_log_column(self):
        columns = [alarms.column(name) for name in alarms.SERIES]
        self.assertEqual(len(columns), len(set(columns)))


class Recording(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / "logs"
        self.reply = json.dumps(state(**{"TAS, km/h": 700})).encode()
        self.watch = alarms.Watch(lambda path: self.reply if path == "/state" else None, lambda: details(),
                                  save=lambda: None, logs=self.folder)
        self.watch.model = lambda: "j_10c"

    def tearDown(self):
        self.watch.set_log(False)
        self.tmp.cleanup()

    def names(self):
        return {alarms.column(n): n for n in alarms.SERIES}

    def test_not_read_when_nobody_wants_it(self):
        self.watch.get = mock.Mock(return_value=self.reply)
        self.watch.tick()
        self.watch.get.assert_not_called()

    def test_the_tab_being_open_is_enough(self):
        self.watch.viewed = time.monotonic()
        with mock.patch.object(alarms, "beep") as beep:
            self.watch.tick()
        self.assertEqual(self.watch.trace[-1]["ias"], 500)
        self.assertEqual(self.watch.display, [])  # the overlay stays off
        beep.assert_not_called()

    def test_a_reading_a_second(self):
        self.watch.viewed = time.monotonic()
        for _ in range(3):
            self.watch.tick()
        self.assertEqual(len(self.watch.trace), 1)
        self.watch._sampled -= 2 * alarms.SAMPLE_S
        self.watch.tick()
        self.assertEqual([r["n"] for r in self.watch.trace], [1, 2])

    def test_a_log(self):
        self.watch.viewed = time.monotonic()
        self.watch.tick()
        self.watch.set_log(True)
        name = self.watch.log.name
        self.assertTrue(name.startswith("j_10c-"))
        self.watch._sampled -= 2 * alarms.SAMPLE_S
        self.watch.tick()
        self.watch.set_log(False)
        raw = (self.folder / name).read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "BOM for Excel")
        self.assertIn('"Time, s","IAS, km/h"', raw.decode("utf-8-sig"))
        rows = flightlog.read_log(self.folder, name, self.names())["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["ias"], rows[0]["vne"]), (500, 1543))

    def test_recording_is_shown_by_its_line(self):
        self.watch.enabled = True
        self.watch.tick()
        self.assertNotIn("REC", [x[0] for x in self.watch.display])
        self.watch.set_log(True)
        self.watch.tick()
        self.assertIn("REC", [x[0] for x in self.watch.display])

    def test_logs_listed_and_deleted(self):
        self.folder.mkdir()
        for name in ("a.csv", "b.csv"):
            (self.folder / name).write_text("x", encoding="utf-8")
        self.assertEqual({x["name"] for x in flightlog.list_logs(self.folder)}, {"a.csv", "b.csv"})
        self.assertTrue(flightlog.delete_log(self.folder, "a.csv"))
        self.assertFalse(flightlog.delete_log(self.folder, "a.csv"))

    def test_names_from_the_page_stay_in_the_folder(self):
        self.folder.mkdir()
        outside = self.folder.parent / "x.csv"
        outside.write_text("Time, s\n1\n", encoding="utf-8")
        for name in ("../x.csv", "..\\x.csv", "C:/x.csv", "x.txt", ""):
            self.assertIsNone(flightlog.read_log(self.folder, name, {}), name)
            self.assertFalse(flightlog.delete_log(self.folder, name), name)
        self.assertTrue(outside.exists())

    def test_a_broken_log_is_refused(self):
        self.folder.mkdir()
        (self.folder / "bad.csv").write_text('"Time, s"\nabc\n', encoding="utf-8")
        self.assertIsNone(flightlog.read_log(self.folder, "bad.csv", {}))

    def test_a_name_is_made_safe(self):
        log = flightlog.Log(self.folder, "a/b:c", ["x"])
        log.close()
        self.assertTrue(log.name.startswith("a_b_c-"))


class Configuration(unittest.TestCase):
    def test_nothing_saved(self):
        for saved in (None, [], "x", 3):
            self.assertEqual(alarms.clean(saved, WORDS), alarms.defaults(WORDS))

    def test_defaults_scale_with_the_screen(self):
        with mock.patch.object(alarms, "screen", return_value=(3840, 2160)):
            self.assertEqual([alarms.defaults(WORDS)[k] for k in ("x", "y", "size")], [700, 55, 40])
        with mock.patch.object(alarms, "screen", return_value=(1920, 1080)):
            self.assertEqual([alarms.defaults(WORDS)[k] for k in ("x", "y", "size")], [350, 28, 20])

    def test_a_setting_survives_with_the_rest_filled_in(self):
        cfg = alarms.clean({"x": 12, "font": "Segoe UI"}, WORDS)
        self.assertEqual((cfg["x"], cfg["font"], cfg["opacity"]), (12, "Segoe UI", 100))
        self.assertEqual(cfg["alarms"]["airframe"]["at"], 93)

    def test_odd_values_fall_back(self):
        cfg = alarms.clean({"x": "a", "size": True, "font": "x;y{}", "color": "red", "alert": "#12", "bold": 1,
                            "hotkey": ["F1"], "lines": "no", "alarms": {"gear": {"at": "x", "hz": None}}}, WORDS)
        self.assertEqual(cfg, alarms.defaults(WORDS))

    def test_numbers_stay_in_range(self):
        cfg = alarms.clean({"size": 1, "opacity": 900, "repeat": 1, "alarms": {"gear": {"at": 900, "hz": 1, "ms": 99999}}}, WORDS)
        self.assertEqual((cfg["size"], cfg["opacity"], cfg["repeat"]), (6, 100, 100))
        self.assertEqual(cfg["alarms"]["gear"], {"on": True, "at": 200, "hz": 37, "ms": 2000})

    def test_lines_are_limited(self):
        cfg = alarms.clean({"lines": [{"text": "x" * 500, "when": "?", "alarm": "?", "color": "?", "size": -3}, "no"] * 40}, WORDS)
        self.assertEqual(len(cfg["lines"]), alarms.MAX_LINES)
        self.assertEqual(cfg["lines"][0], {"text": "x" * alarms.MAX_TEXT, "when": "always", "alarm": "", "color": "", "size": 0})

    def test_no_lines_at_all_is_a_choice(self):
        self.assertEqual(alarms.clean({"lines": []}, WORDS)["lines"], [])

    def test_a_show_hide_key(self):
        cfg = alarms.clean({"hotkey": [17, 123], "hotkeyName": "Ctrl+F12"}, WORDS)
        self.assertEqual((cfg["hotkey"], cfg["hotkeyName"]), ([17, 123], "Ctrl+F12"))
        self.assertEqual(alarms.clean({"hotkey": [1000]}, WORDS)["hotkey"], [])

    def test_every_value_of_the_default_lines_exists(self):
        names = {n for line in alarms.defaults(WORDS)["lines"] for n, _ in alarms.FIELD.findall(line["text"])}
        self.assertLessEqual(names, set(alarms.FIELDS) | set(alarms.COMPUTED) | {"swept"})

    def test_every_value_of_the_page_exists(self):
        page = (alarms.WEB / "overlay.js").read_text(encoding="utf-8")
        names = set(re.findall(r"'(\w+)'", page[page.index("OV_VALUES = {"):page.index("function ovShow")]))
        self.assertTrue(names)
        self.assertLessEqual(names, set(alarms.FIELDS) | set(alarms.COMPUTED) | {"swept", "fuel_time"})


class Preview(unittest.TestCase):
    def setUp(self):
        self.watch = alarms.Watch(lambda path: None, dict, save=lambda: None)
        self.watch.start_overlay = lambda: None

    def test_sample_lines_show_all_with_an_alarm_on(self):
        lines = self.watch.sample(self.watch.cfg)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[2], ("GEAR   640 / 700 km/h", self.watch.cfg["alert"], self.watch.cfg["size"]))

    def test_shown_without_the_game_then_taken_off(self):
        self.watch.set_preview(self.watch.cfg)
        self.watch.tick()
        self.assertEqual(self.watch.display, self.watch.sample(self.watch.cfg))
        self.watch.set_preview(None)
        self.watch.tick()
        self.assertEqual(self.watch.display, [])

    def test_shows_the_overlay_being_edited(self):
        self.watch.set_preview(alarms.clean({"lines": [{"text": "hello"}]}, WORDS))
        self.assertEqual(self.watch.display[0][0], "hello")


class Profiles(unittest.TestCase):
    def setUp(self):
        self.jet = alarms.clean({"lines": [{"text": "J-10"}]}, WORDS)
        self.fighters = alarms.clean({"lines": [{"text": "fighter"}]}, WORDS)
        self.reply = json.dumps(state()).encode()
        self.indicators = b'{"valid": true, "type": "j_10c"}'
        kinds = {"j_10c": "fighter", "j_10a": "fighter", "su_30mkk": "bomber"}
        self.watch = alarms.Watch(lambda path: self.indicators if path == "/indicators" else self.reply, details,
                                  save=lambda: None, kind=kinds.get)
        self.watch.enabled = True
        self.watch.start_overlay = lambda: None

    def texts(self):
        return [x[0] for x in self.watch.display]

    def test_the_aircraft_s_own_comes_first(self):
        self.watch.set_config(self.watch.base, {"j_10c": self.jet, "type:fighter": self.fighters})
        self.watch.tick()
        self.assertEqual((self.watch.current, self.watch.profile, self.texts()), ("j_10c", "j_10c", ["J-10"]))

    def test_then_its_type(self):
        self.watch.set_config(self.watch.base, {"type:fighter": self.fighters})
        self.watch.tick()
        self.assertEqual((self.watch.profile, self.texts()), ("type:fighter", ["fighter"]))

    def test_then_the_one_for_all_aircraft(self):
        self.watch.set_config(self.watch.base, {"su_30mkk": self.jet, "type:bomber": self.fighters})
        self.watch.tick()
        self.assertEqual(self.watch.profile, "")
        self.assertEqual(self.texts()[0], "IAS    500 / 1543 km/h")

    def test_alarms_are_the_profile_s_too(self):
        self.watch.set_config(self.watch.base, {"j_10c": alarms.clean({"alarms": {"airframe": {"at": 30, "hz": 500, "ms": 80}}}, WORDS)})
        with mock.patch.object(alarms, "beep") as beep:
            self.watch.tick()
        beep.assert_called_once_with(500, 80)

    def test_back_in_the_hangar(self):
        self.watch.set_config(self.watch.base, {"j_10c": self.jet})
        self.watch.tick()
        self.reply = b'{"valid": false}'
        self.watch.tick()
        self.assertEqual((self.watch.current, self.watch.profile, self.watch.cfg), (None, "", self.watch.base))

    def test_changed_while_flying(self):
        self.watch.tick()
        self.watch.set_config(self.watch.base, {"j_10c": self.jet})
        self.watch.tick()
        self.assertEqual(self.texts(), ["J-10"])

    def test_profile_names(self):
        for good in ("j_10c", "a-20g", "type:fighter"):
            self.assertTrue(alarms.PROFILE.fullmatch(good), good)
        for bad in ("", "../x", "a b", "type:", "x:y"):
            self.assertFalse(alarms.PROFILE.fullmatch(bad), bad)


class Battle(unittest.TestCase):
    def get(self, path):
        self.asked.append(path)
        return self.answers.get(path.split("?")[0])

    def setUp(self):
        self.asked = []
        self.answers = {
            "/gamechat": json.dumps([{"id": 7, "msg": "<color=#ff0000>hi</color> <b>there", "sender": "Bob\ue001", "enemy": True,
                                      "mode": "All", "time": 12}]).encode(),
            "/hudmsg": json.dumps({"events": [], "damage": [{"id": 3, "msg": "=FrEB= Pilot (\u2417Su-30MKK) s'est \u00e9cras\u00e9.",
                                                             "sender": "", "enemy": False, "mode": "", "time": 1417}]}).encode()}

    def test_asks_after_the_page_s_last_look(self):
        battle.news(self.get, 7, 2, 3)
        self.assertEqual(self.asked, ["/gamechat?lastId=7", "/hudmsg?lastEvt=2&lastDmg=3"])

    def test_text_comes_clean(self):
        out = battle.news(self.get, 0, 0, 0)
        self.assertEqual(out["chat"], [{"id": 7, "time": 12, "text": "hi there", "sender": "Bob", "enemy": True, "mode": "All"}])
        self.assertEqual(out["damage"][0]["text"], "=FrEB= Pilot (Su-30MKK) s'est \u00e9cras\u00e9.")
        self.assertTrue(out["up"])

    def test_game_closed(self):
        self.answers = {}
        self.assertEqual(battle.news(self.get, 1, 2, 3), {"up": False, "chat": [], "events": [], "damage": []})

    def test_bad_answers(self):
        self.answers = {"/gamechat": b"not json", "/hudmsg": b"[1, 2]"}
        self.assertEqual(battle.news(self.get, 0, 0, 0)["damage"], [])
        self.answers = {"/gamechat": b'{"a": 1}', "/hudmsg": b'{"damage": ["x", 3]}'}
        out = battle.news(self.get, 0, 0, 0)
        self.assertEqual((out["chat"], out["damage"]), ([], []))


class Labels(unittest.TestCase):
    def test_every_language_has_every_word(self):
        en = alarms.labels("en")
        self.assertEqual(set(en), {"gear", "flaps", "swept", "unknown", "unbreakable"})
        for path in Path(alarms.WEB / "locales").glob("*.json"):
            if path.stem != "index":
                self.assertEqual(set(alarms.labels(path.stem)), set(en), path.stem)

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(alarms.labels("xx")["gear"], "GEAR")
        self.assertEqual(alarms.labels("../secrets")["gear"], "GEAR")

    def test_translated(self):
        self.assertEqual(alarms.labels("fr")["gear"], "TRAIN")


if __name__ == "__main__":
    unittest.main()
