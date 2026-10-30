"""Offline US city -> (lat, lng) lookup, so no geocoding API calls are needed."""
import csv
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings

CITIES_CSV = Path(settings.BASE_DIR) / "data" / "us_cities.csv"


def norm(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"\bsaint\b", "st", name)
    name = re.sub(r"\bst\.", "st", name)
    name = re.sub(r"\bmount\b", "mt", name)
    name = re.sub(r"\bfort\b", "ft", name)
    return re.sub(r"[^a-z0-9 ]", "", name).strip()


@lru_cache(maxsize=1)
def _index():
    idx, state_pts = {}, {}
    with open(CITIES_CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pt = (float(row["LATITUDE"]), float(row["LONGITUDE"]))
            idx.setdefault((norm(row["CITY"]), row["STATE_CODE"]), pt)
            state_pts.setdefault(row["STATE_CODE"], []).append(pt)
    return idx


def lookup(city: str, state: str):
    return _index().get((norm(city), state.upper().strip()))


def states():
    return {s for (_, s) in _index()}
