"""Flight logs: readings recorded on demand as CSV files (user/logs), UTF-8 with a BOM so that Excel reads them right."""
from __future__ import annotations

import csv
import re
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


def delete_log(folder: Path, name: str) -> bool:
    if not NAME.fullmatch(name):
        return False
    try:
        (folder / name).unlink()
        return True
    except OSError:
        return False
