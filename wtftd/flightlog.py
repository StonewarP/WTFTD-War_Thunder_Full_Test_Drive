"""Flight logs: readings recorded on demand as CSV files (user/logs), UTF-8 with a BOM so that Excel reads them right."""
from __future__ import annotations

import csv
import math
import re
import statistics
import time
from pathlib import Path

NAME = re.compile(r"[\w.\-]{1,120}\.csv")
TIME = "Time, s"


class Log:
    def __init__(self, folder: Path, flight: str, columns: list):
        folder.mkdir(parents=True, exist_ok=True)
        self.name = f"{re.sub(r'[^\w.\-]', '_', flight)[:60]}-{time.strftime('%Y_%m_%d_%H_%M_%S')}.csv"
        self.file = open(folder / self.name, "w", encoding="utf-8-sig", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow([TIME, *columns])
        self.start = time.monotonic()

    def write(self, values: list):
        self.writer.writerow([round(time.monotonic() - self.start, 1), *values])
        self.file.flush()  # a crash of the game or the PC loses nothing

    def close(self):
        self.file.close()


def list_logs(folder: Path) -> list:
    """Newest first."""
    out = [{"name": p.name, "size": p.stat().st_size, "time": int(p.stat().st_mtime)} for p in folder.glob("*.csv")]
    return sorted(out, key=lambda x: -x["time"])


def read_log(folder: Path, name: str, names: dict) -> dict | None:
    """A log's rows for the curves: {"rows": [{"t": seconds, value name: number...}]}; names: column -> value name.
    None if it isn't one of ours (the name comes from the page)."""
    if not NAME.fullmatch(name):
        return None
    try:
        with open(folder / name, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            keys = ["t" if c == TIME else names.get(c) for c in next(reader, [])]
            return {"rows": [{k: float(v) for k, v in zip(keys, row) if k and v} for row in reader]}
    except (OSError, ValueError):
        return None


LEVEL_VY, STEADY, TURNING_G, RUN_S = 2.0, 0.5, 1.5, 3  # a sustained turn: m/s of climb, m/s2 of acceleration, load factor, seconds
CLIMB_TO = (1000, 3000, 5000, 7000, 9000, 11000)  # altitudes whose time to climb is reported (m)


def report(rows: list) -> dict:
    """A flight's numbers, from the rows read_log gives: its peaks (each with the speed and altitude it happened at),
    the time to climb to some altitudes, the fuel used, and the best sustained turn: level, at a steady speed and pulling
    more than TURNING_G for at least RUN_S seconds, its turn rate the median of that stretch."""
    rows = [r for r in rows if "t" in r]
    if len(rows) < 2:
        return {}

    def peak(key, *context):
        have = [r for r in rows if key in r]
        best = max(have, key=lambda r: r[key], default=None)
        return best and {"v": best[key], **{k: best[k] for k in context if k in best}}

    out = {"s": round(rows[-1]["t"] - rows[0]["t"]), "ias": peak("ias", "alt"), "mach": peak("mach", "alt", "ias"), "alt": peak("alt"),
           "climb": peak("vy", "ias", "alt"), "g": peak("g", "ias", "alt"), "turn": peak("turn_rate", "ias", "alt", "g")}
    first = rows[0].get("alt")
    out["climbTo"] = []
    for a in CLIMB_TO:
        reached = next((r for r in rows if r.get("alt", 0) >= a), None)
        if first is not None and first < a - 100 and reached:
            out["climbTo"].append([a, round(reached["t"] - rows[0]["t"])])
    fuel = [r["fuel"] for r in rows if "fuel" in r]
    if len(fuel) > 1:
        out["fuel"] = round(fuel[0] - fuel[-1])
    out["sustained"], run = None, []
    for r in [*rows, {}]:
        if all(k in r for k in ("vy", "accel", "g", "turn_rate")) and abs(r["vy"]) < LEVEL_VY and abs(r["accel"]) < STEADY and r["g"] > TURNING_G:
            run.append(r)
            continue
        if len(run) >= RUN_S:
            rate = statistics.median(x["turn_rate"] for x in run)
            if out["sustained"] is None or rate > out["sustained"]["v"]:
                out["sustained"] = {"v": rate, "s": len(run), **{k: statistics.median(x[k] for x in run if k in x) for k in ("ias", "alt", "g") if any(k in x for x in run)}}
        run = []
    return out


def started(folder: Path, name: str) -> float:
    """When a log began: the time in its name, else its file's."""
    try:
        return time.mktime(time.strptime(name[-23:-4], "%Y_%m_%d_%H_%M_%S"))
    except ValueError:
        return (folder / name).stat().st_mtime


def acmi(rows: list, flight: str, start: float) -> str | None:
    """A flight as a Tacview text file (ACMI 2.2), your own aircraft only. The game's map is flat, so the track is
    laid around longitude 0, latitude 0. Pitch is the path angle plus the angle of attack; the roll isn't given (the
    game's sign isn't checked). None when the log has no position, as those recorded before it was kept."""
    pts = [r for r in rows if "east" in r and "north" in r and "alt" in r]
    if not pts:
        return None
    e0, n0 = pts[0]["east"], pts[0]["north"]
    out = ["FileType=text/acmi/tacview", "FileVersion=2.2",
           f"0,ReferenceTime={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(start))}", f"0,Title={flight}"]
    for i, r in enumerate(pts):
        tas = r.get("tas", 0) / 3.6
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, r.get("vy", 0) / tas)))) + r.get("aoa", 0) if tas > 20 else None
        spot = "|".join([f"{(r['east'] - e0) / 111320:.7f}", f"{(r['north'] - n0) / 110574:.7f}", f"{r['alt']:.1f}", "",
                         "" if pitch is None else f"{pitch:.1f}", f"{r['hdg']:.1f}" if "hdg" in r else ""])
        out += [f"#{r['t']:.1f}", f"1,T={spot}" + (f",Name={flight},Type=Air+FixedWing,Color=Blue" if i == 0 else "")]
    return "\n".join(out) + "\n"


def delete_log(folder: Path, name: str) -> bool:
    if not NAME.fullmatch(name):
        return False
    try:
        (folder / name).unlink()
        return True
    except OSError:
        return False
