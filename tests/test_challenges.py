"""Challenges: each generated mission reads back with its objective, timer and ends, using only what the game's own missions use."""
import json
import re
import unittest
from unittest import mock

from wtftd import blk, builder, challenges, mission, paths

GOAL = "T-72A: destroy them"
LANGS = ("en", "fr", "de", "ru", "pl", "es", "pt", "it", "cs", "zh", "ja")
# what these missions name: each is in the game's own missions (OfficialNames checks it where the game files are)
ACTIONS = {"missionCompleted", "missionFailed", "missionMarkAsWaypoint", "missionRestart", "missionSetTargetsIndicator", "missionSetTimeIndicator",
           "moAddMissionObjective", "moSetObjectiveStatus", "playHint", "triggerDisable", "triggerEnable", "unitAttackTarget", "unitRespawn", "unitSetIndication",
           "unitSetProperties", "varModify", "wait"}
CONDITIONS = {"playerShortcutPressed", "playersDistanceBetween", "playersWhenStatus", "unitWhenCountMatches", "varCompareInt"}
EVENTS = {"initMission", "periodicEvent"}


def vehicle(vid, cat, kind, br=8.0):
    return {"id": vid, "c": cat, "k": kind, "br": [br, br, br], "n": "ussr", "r": 5, "wg": ["gun"], "s": {"spd": 900}}


VEHICLES = {v["id"]: v for v in (vehicle("tank_a", "ground", "tank"), vehicle("tank_b", "ground", "heavy_tank", 8.3), vehicle("radar_fcs", "ground", "tank", 8.0),
                                 vehicle("jet_a", "air", "fighter"), vehicle("jet_b", "air", "fighter", 8.7), vehicle("heli_a", "heli", ""),
                                 vehicle("ship_a", "ship", "destroyer"), vehicle("boat_a", "boat", "gun_boat"))}
BY_CAT = {"ground": "tank_a", "air": "jet_a", "heli": "heli_a", "ship": "ship_a", "boat": "boat_a"}
BLOCKS = {"ground": "tankModels", "air": "armada", "heli": "armada", "ship": "ships", "boat": "ships"}


def scenario(sid):
    block = BLOCKS[sid.rsplit("_", 1)[1]]
    return builder._hangar_mission("x", block, [1.0, 2.0, 3.0], "WTFTD")


def body(cid, diff="normal", level=None, cat=None, **more):
    c = challenges.CHALLENGES[cid]
    cat = cat or c["cats"][0]
    return {"vehicle": BY_CAT[cat], "block": BLOCKS[cat], "speed": 600, "cheats": {"immortal": True, "crew": "ace"}, **more,
            "challenge": {"id": cid, "diff": diff, "level": level or c["sites"][0]["level"], "texts": {"goal": GOAL, "start": "Go", "gate": "Gate {n} of {total}", "wave": "Wave {n}"}}}


def build(*a, **k):
    with mock.patch.object(mission, "load_scenario", scenario):
        return mission.build(challenges.plan(body(*a, **k), VEHICLES))


def triggers(m):
    return {k: t for k, t in m["triggers"].items() if isinstance(t, dict)}


def every_build():
    for cid, c in challenges.CHALLENGES.items():
        for cat in c["cats"]:
            for diff in challenges.DIFFICULTIES:
                for site in c["sites"]:
                    yield cid, diff, site["level"], cat


class Missions(unittest.TestCase):
    def test_each_one_reads_back_with_its_goal_timer_and_ends(self):
        for cid, diff, level, cat in every_build():
            with self.subTest(cid=cid, diff=diff, level=level, cat=cat):
                name, text = build(cid, diff, level, cat)
                self.assertTrue(name.startswith(f"wtftd_ch-{cid}-{diff}-"))
                m = blk.loads(text)
                self.assertEqual(m["mission_objectives"][GOAL]["type"], "abstractMissionObjective")
                self.assertTrue(m["mission_objectives"][GOAL]["props"]["isPrimary"])
                t = triggers(m)
                self.assertEqual(t["wtftd_ch_start"]["actions"]["moAddMissionObjective"]["target"], GOAL)
                self.assertEqual(t["wtftd_ch_clock"]["actions"]["missionSetTimeIndicator"]["var"], mission.CH_TIME)
                self.assertGreater(m["variables"][mission.CH_TIME], 0)
                self.assertEqual(m["variables"][mission.CH_NO_TIME], 0)
                self.assertEqual(t["wtftd_ch_time_up"]["conditions"]["varCompareInt"]["var_value"], mission.CH_TIME)
                self.assertIn("missionFailed", t["wtftd_ch_dead"]["actions"])
                self.assertEqual(t["wtftd_ch_restart"]["conditions"]["playerShortcutPressed"]["control"], "ID_FAST_VOICE_MESSAGE_7")
                self.assertNotIn("wtftd_respawn", t)  # a death ends it
                self.assertTrue(any("missionCompleted" in x["actions"] for x in t.values()))
                for x in t.values():
                    for a in ("missionCompleted", "missionFailed"):
                        if a in x["actions"]:
                            self.assertEqual(x["actions"]["moSetObjectiveStatus"]["target"], GOAL)
                            self.assertEqual(x["actions"]["moSetObjectiveStatus"]["status"], 2 if a == "missionCompleted" else 3)
                            self.assertEqual(x["actions"]["missionSetTimeIndicator"]["var"], mission.CH_NO_TIME)

    def test_only_what_the_game_uses(self):
        for args in every_build():
            m = blk.loads(build(*args)[1])
            for t in triggers(m).values():
                if str(t.get("comments")) != "WTFTD":
                    continue
                self.assertLessEqual(set(t["actions"]), ACTIONS)
                self.assertLessEqual(set(t["conditions"]), CONDITIONS)
                self.assertLessEqual(set(t["events"]), EVENTS)

    def test_one_ending_stops_the_others(self):
        t = triggers(blk.loads(build("range")[1]))
        self.assertEqual(sorted(t["wtftd_ch_dead"]["actions"]["triggerDisable"]["target"]), ["wtftd_ch_clock", "wtftd_ch_time_up", "wtftd_ch_won"])
        self.assertEqual(sorted(t["wtftd_ch_won"]["actions"]["triggerDisable"]["target"]), ["wtftd_ch_clock", "wtftd_ch_dead", "wtftd_ch_time_up"])

    def test_targets_are_a_squad_of_real_units(self):
        m = blk.loads(build("range", "hard")[1])
        squad = m["units"]["squad"]
        self.assertEqual(squad["name"], "wtftd_ch_targets")
        self.assertEqual(len(squad["props"]["squad_members"]), 5)
        trucks = {u["name"]: u for u in m["units"]["wheeled_vehicles"]}
        self.assertLessEqual(set(squad["props"]["squad_members"]), set(trucks))
        self.assertEqual(triggers(m)["wtftd_ch_won"]["conditions"]["unitWhenCountMatches"]["object"], "wtftd_ch_targets")

    def test_gates_go_one_after_the_other(self):
        m = blk.loads(build("gates", "easy")[1])
        t = triggers(m)
        self.assertTrue(t["wtftd_ch_gate_1_passed"]["is_enabled"])
        self.assertFalse(t["wtftd_ch_gate_2_passed"]["is_enabled"])
        self.assertEqual(t["wtftd_ch_gate_1_passed"]["actions"]["triggerEnable"]["target"], "wtftd_ch_gate_2_passed")
        self.assertEqual(t["wtftd_ch_start"]["actions"]["missionMarkAsWaypoint"]["target"], "wtftd_ch_gate_1")
        marks = t["wtftd_ch_gate_1_passed"]["actions"]["missionMarkAsWaypoint"]
        self.assertEqual([(x["target"], x["visible"]) for x in marks], [("wtftd_ch_gate_1", False), ("wtftd_ch_gate_2", True)])
        self.assertIn("missionCompleted", t["wtftd_ch_gate_6_passed"]["actions"])
        self.assertEqual(t["wtftd_ch_gate_3_passed"]["actions"]["playHint"]["name"], "Gate 3 of 6")
        self.assertEqual(m["areas"]["wtftd_ch_gate_6"]["type"], "Point")
        self.assertEqual(t["wtftd_ch_gate_1_passed"]["conditions"]["playersDistanceBetween"]["value"], 400.0)

    def test_the_time_allowed_follows_the_aircraft(self):
        slow, fast = dict(VEHICLES["jet_a"], s={"spd": 300}), dict(VEHICLES["jet_a"], s={"spd": 2000})
        limits = [challenges.plan(body("gates", "hard"), {**VEHICLES, "jet_a": v})["_challenge"]["limit"] for v in (slow, fast)]
        self.assertGreater(limits[0], limits[1])
        self.assertEqual(limits[1] % 10, 0)

    def test_waves_win_on_the_last_one_only(self):
        t = triggers(blk.loads(build("dogfight", "normal")[1]))
        self.assertFalse(t["wtftd_ch_won"]["is_enabled"])  # the last wave isn't there yet: it would count as destroyed
        self.assertEqual(t["wtftd_ch_won"]["conditions"]["unitWhenCountMatches"]["object"], "wtftd_wave_3")
        self.assertEqual(t["wtftd_wave_2_end"]["actions"]["triggerEnable"]["target"], "wtftd_ch_won")
        self.assertEqual(t["wtftd_wave_1_end"]["actions"]["triggerEnable"]["target"], "wtftd_wave_2_end")

    def test_evasion_wins_when_the_timer_runs_out(self):
        m = blk.loads(build("evasion", "hard")[1])
        t = triggers(m)
        self.assertIn("missionCompleted", t["wtftd_ch_time_up"]["actions"])
        self.assertNotIn("wtftd_ch_won", t)
        attacks = t["wtftd_ch_attack"]["actions"]["unitAttackTarget"]
        self.assertEqual(len(attacks), 3)
        self.assertEqual(attacks[0]["attack_type"], "attack_target")
        self.assertEqual(m["units"]["armada"][1]["weapons"], challenges.MISSILES[1])

    def test_time_up_fails_the_others(self):
        self.assertIn("missionFailed", triggers(blk.loads(build("bombing")[1]))["wtftd_ch_time_up"]["actions"])


class Plan(unittest.TestCase):
    def plan(self, *a, **k):
        return challenges.plan(body(*a, **k), VEHICLES)

    def test_cheats_stay_out_the_crew_stays(self):
        self.assertEqual(self.plan("range")["cheats"], {"crew": "ace"})

    def test_a_vehicle_it_does_not_fit_is_refused(self):
        b = body("range")
        b["vehicle"] = "jet_a"
        with self.assertRaises(mission.MissionError):
            challenges.plan(b, VEHICLES)

    def test_a_bad_request_is_refused(self):
        for ask in ({"id": "nope"}, {"id": "range", "diff": "brutal", "level": "avg_training_ground"}, {"id": "range", "diff": "easy", "level": "air_afghan"}, {}):
            with self.subTest(ask=ask), self.assertRaises(mission.MissionError):
                challenges.plan({"vehicle": "tank_a", "challenge": ask}, VEHICLES)

    def test_scenario_by_map_and_kind(self):
        self.assertEqual(self.plan("naval", "easy", "avn_alps_fjord", "boat")["scenario"], "free_avn_alps_fjord_boat")

    def test_targets_stand_on_the_sites_line_at_their_distance(self):
        site = challenges.LAND[0]
        trucks = self.plan("range", "easy")["edits"]["add"]
        x, _, z = site["start"]
        self.assertEqual(site["yaw"], 0.0)  # along +x, as mission._yaw_tm turns a unit
        self.assertAlmostEqual(trucks[1]["x"] - x, 600, delta=1)
        self.assertAlmostEqual(trucks[1]["z"] - z, -63, delta=1)
        self.assertAlmostEqual(trucks[1]["y"], 217.7, delta=0.1)

    def test_foes_are_near_the_players_rating_and_fire(self):
        self.assertEqual(challenges._foes(VEHICLES, VEHICLES["tank_a"], ("tank", "heavy_tank"), 3), ["tank_b"])  # no radar, not the player's own

    def test_a_vehicle_without_a_rating_still_gets_foes(self):
        self.assertTrue(challenges._foes(VEHICLES, {"id": "x", "c": "air"}, ("fighter",), 2))

    def test_the_objective_is_remembered_as_the_mission_writes_it(self):
        b = body("range")
        b["challenge"]["texts"]["goal"] = '  A "quoted"   goal '
        data = challenges.clean(None)
        challenges.remember(data, b)
        with mock.patch.object(mission, "load_scenario", scenario):
            m = blk.loads(mission.build(challenges.plan(b, VEHICLES))[1])
        self.assertIn(next(iter(data["made"])), m["mission_objectives"])


class Live(unittest.TestCase):
    made = {GOAL: {"id": "range", "diff": "hard", "level": "avg_training_ground", "vehicle": "tank_a"}}

    def state(self, status, text=GOAL):
        # as the game answers, read during a real battle: objectives not started yet are listed too
        return json.dumps({"objectives": [{"primary": True, "status": status, "text": text}, {"primary": True, "status": "undefined", "text": text}], "status": "running"}).encode()

    def test_a_win_and_its_time(self):
        live = challenges.Live()
        self.assertIsNone(live.tick(self.state("undefined"), self.made, 90.0))
        self.assertIsNone(live.tick(self.state("in_progress"), self.made, 100.0))
        self.assertIsNone(live.tick(self.state("in_progress"), self.made, 150.0))
        done = live.tick(self.state("completed"), self.made, 162.4)
        self.assertEqual((done["result"], done["time"], done["id"], done["vehicle"]), ("win", 62, "range", "tank_a"))
        self.assertIsNone(live.tick(self.state("completed"), self.made, 163.0))  # once

    def test_a_failure(self):
        live = challenges.Live()
        live.tick(self.state("in_progress"), self.made, 100.0)
        self.assertEqual(live.tick(self.state("failed"), self.made, 110.0)["result"], "loss")

    def test_another_mission_is_nobodys(self):
        live = challenges.Live()
        self.assertIsNone(live.tick(self.state("in_progress", "Aidez les forces au sol"), self.made, 100.0))
        self.assertIsNone(live.tick(self.state("completed", "Aidez les forces au sol"), self.made, 110.0))

    def test_a_result_seen_without_its_start_is_left_out(self):
        self.assertIsNone(challenges.Live().tick(self.state("completed"), self.made, 110.0))

    def test_starting_over_starts_the_clock_over(self):
        live = challenges.Live()
        live.tick(self.state("in_progress"), self.made, 100.0)
        live.tick(None, self.made, 110.0)  # the mission loads again
        live.tick(self.state("in_progress"), self.made, 120.0)
        self.assertEqual(live.tick(self.state("completed"), self.made, 130.0)["time"], 10)

    def test_no_game_or_no_mission(self):
        for raw in (None, b"", b"not json", b"[]", b'{"objectives": null, "status": "fail"}'):
            self.assertIsNone(challenges.Live().tick(raw, self.made, 1.0))


class Merge(unittest.TestCase):
    def row(self, **k):
        return {"file": "a.wrpl", "vehicles": ["tank_a"], "challenge": ["range", "hard"], "start": 1000, "played": 63, "level": "avg_training_ground", "result": "left", **k}

    def data(self, **k):
        return {"made": {}, "results": [{"id": "range", "diff": "hard", "vehicle": "tank_a", "level": "avg_training_ground", "result": "win", "time": 70, "at": 1062, **k}]}

    def test_the_replay_gives_the_exact_time_and_the_row_its_result(self):
        data, row = self.data(), self.row()
        self.assertTrue(challenges.merge(data, [row]))
        self.assertEqual((data["results"][0]["time"], data["results"][0]["file"]), (60, "a.wrpl"))
        self.assertEqual(row["result"], "win")
        row = self.row()
        self.assertFalse(challenges.merge(data, [row]))  # the next look changes nothing
        self.assertEqual(row["result"], "win")

    def test_a_replay_with_a_result_counts_without_the_app(self):
        data = challenges.clean(None)
        self.assertTrue(challenges.merge(data, [self.row(result="win")]))
        self.assertEqual((data["results"][0]["time"], data["results"][0]["result"]), (60, "win"))

    def test_a_replay_left_early_counts_for_nothing(self):
        data = challenges.clean(None)
        self.assertFalse(challenges.merge(data, [self.row()]))
        self.assertEqual(data["results"], [])

    def test_another_battle_is_left_alone(self):
        data = self.data()
        row = {"file": "b.wrpl", "vehicles": ["x"], "start": 1, "played": 2, "result": "win"}
        self.assertFalse(challenges.merge(data, [row]))

    def test_a_result_far_from_the_replay_is_another_try(self):
        data = self.data(at=5000)
        self.assertFalse(challenges.merge(data, [self.row()]))

    def test_the_list_stays_bounded(self):
        data = challenges.clean(None)
        for i in range(challenges.MAX_RESULTS + 5):
            challenges.add_result(data, {"at": i})
        self.assertEqual(len(data["results"]), challenges.MAX_RESULTS)
        self.assertEqual(data["results"][-1]["at"], challenges.MAX_RESULTS + 4)


    def test_a_damaged_file_does_not_stop_My_battles(self):
        for broken in (None, [], "x", {"made": 3, "results": 4}, {"made": {}, "results": ["x", {"id": "range"}]}):
            data = challenges.clean(broken)
            self.assertEqual(data, {"made": {}, "results": []})
            self.assertFalse(challenges.merge(data, [self.row()]))


class Texts(unittest.TestCase):
    def test_every_challenge_is_worded_in_every_language(self):
        keys = {"nav.challenges", "share.kind.challenge", "share.importedHint.challenge"} | {f"cg.{d}" for d in ("hint", "how", "best", "done", "noResult", "noResults", "results", "challenge", "level", "bestTime", "tries", "again", "needs", "missionTitle", "goal", "desc", "start", "gate")}
        keys |= {f"cg.diff.{d}" for d in challenges.DIFFICULTIES} | {f"cg.{c}" for c in challenges.CHALLENGES} | {f"cg.{c}.rule" for c in challenges.CHALLENGES}
        en = json.loads((paths.WEB / "locales" / "en.json").read_text(encoding="utf-8"))
        marks = lambda s: set(re.findall(r"\{\w+\}", s))  # noqa: E731
        for lang in LANGS:
            d = json.loads((paths.WEB / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
            for k in keys:
                self.assertTrue(d.get(k), (lang, k))
                self.assertEqual(marks(d[k]), marks(en[k]), (lang, k))


@unittest.skipUnless((paths.DATA / "scenarios.json").exists(), "needs the game data")
class Sites(unittest.TestCase):
    def test_each_site_has_its_bare_map(self):
        known = {s["id"] for s in json.loads((paths.DATA / "scenarios.json").read_text(encoding="utf-8"))}
        for c in challenges.CHALLENGES.values():
            for site in c["sites"]:
                for cat in c["cats"]:
                    self.assertIn(f"free_{site['level']}_{cat}", known)

    def test_the_vehicles_named_exist(self):
        ids = {v["id"] for v in json.loads((paths.DATA / "vehicles.json").read_text(encoding="utf-8"))}
        self.assertLessEqual({challenges.BOAT, challenges.MISSILES[0]}, ids)
        names = {o["id"] for o in json.loads((paths.DATA / "objects.json").read_text(encoding="utf-8"))}
        self.assertIn(challenges.TRUCK, names)


MISSIONS = paths.CACHE / "gamefiles" / "mis.vromfs.bin_u" / "gamedata" / "missions"


@unittest.skipUnless(MISSIONS.exists(), "needs the game's files")
class OfficialNames(unittest.TestCase):
    def test_the_game_uses_each_name_these_missions_use(self):
        seen = {"actions": set(), "conditions": set(), "events": set()}
        for p in MISSIONS.rglob("*.blkx"):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            tr = m.get("triggers") if isinstance(m, dict) else None
            for t in tr.values() if isinstance(tr, dict) else ():
                if isinstance(t, dict):
                    for k, names in seen.items():
                        names |= set(t.get(k) or {}) if isinstance(t.get(k), dict) else set()
        self.assertLessEqual(ACTIONS, seen["actions"])
        self.assertLessEqual(CONDITIONS, seen["conditions"])
        self.assertLessEqual(EVENTS, seen["events"])
