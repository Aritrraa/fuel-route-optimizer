"""Greedy cheapest-fuel planner (classic gas-station problem).

Rules, with the tank measured in miles of range:
  * At a station, if a cheaper station is reachable on a full tank, buy only enough
    to reach the *nearest* cheaper one (fuel is cheaper there).
  * Otherwise fill up and drive to the cheapest station within range.
  * The destination is a price-0 sentinel so we never buy more than needed to arrive.
  * The trip starts with `initial_range` miles of fuel already in the tank (full by
    default) - that fuel is not billed; only fuel bought en route is.
"""
from dataclasses import dataclass


class InfeasibleRoute(Exception):
    pass


@dataclass
class Candidate:
    mile: float
    price: float
    ref: object = None


def plan(candidates, total_miles, max_range=500.0, mpg=10.0, initial_range=None):
    fuel = max_range if initial_range is None else min(initial_range, max_range)
    stations = sorted(candidates, key=lambda c: c.mile)
    dest = Candidate(total_miles, 0.0, None)
    pts = stations + [dest]
    pos, cur_price, cur = 0.0, None, None
    stops = []

    while True:
        if cur is None:  # at origin, not a station
            reach = [c for c in pts if pos < c.mile <= pos + fuel + 1e-9]
        else:
            reach = [c for c in pts if pos < c.mile <= pos + max_range + 1e-9]
        if not reach:
            raise InfeasibleRoute(
                f"No fuel station within {max_range:.0f} miles after mile {pos:.0f}; "
                "try increasing CORRIDOR_MILES.")
        if cur is None:
            nxt = min(reach, key=lambda c: (c.price, -c.mile))
            buy = 0.0
        else:
            cheaper = [c for c in reach if c.price < cur_price]
            if cheaper:
                nxt = cheaper[0]  # nearest cheaper
                buy = max(0.0, (nxt.mile - pos) - fuel)
            else:
                nxt = min(reach, key=lambda c: (c.price, -c.mile))
                buy = max_range - fuel
            if buy > 1e-9:
                stops.append({
                    "station": cur.ref,
                    "mile": cur.mile,
                    "price": cur.price,
                    "gallons": buy / mpg,
                    "cost": buy / mpg * cur.price,
                    "range_before_miles": round(fuel, 1),
                    "range_after_miles": round(fuel + buy, 1),
                })
                fuel += buy
        fuel -= nxt.mile - pos
        pos = nxt.mile
        if nxt is dest:
            return stops
        cur, cur_price = nxt, nxt.price


def build_journey_timeline(stops, total_miles, max_range=500.0, initial_range=None, mpg=10.0):
    """Builds a step-by-step fuel level profile for the entire trip."""
    init = max_range if initial_range is None else min(initial_range, max_range)
    timeline = [{
        "mile": 0.0,
        "fuel_miles": round(init, 1),
        "fuel_percent": round((init / max_range) * 100, 1) if max_range else 100.0,
        "event": "start",
        "label": "Trip Start (Full Tank)"
    }]

    last_mile = 0.0
    last_fuel = init

    for s in stops:
        s_mile = s.get("mile") if s.get("mile") is not None else s.get("mile_marker", 0.0)
        before = s.get("range_before_miles", max(0.0, last_fuel - (s_mile - last_mile)))
        after = s.get("range_after_miles", before + s["gallons"] * mpg)

        timeline.append({
            "mile": round(s_mile, 1),
            "fuel_miles": round(before, 1),
            "fuel_percent": round((before / max_range) * 100, 1) if max_range else 0.0,
            "event": "stop_arrival",
            "label": f"Arrive at Stop #{s.get('stop', '')}"
        })
        timeline.append({
            "mile": round(s_mile, 1),
            "fuel_miles": round(after, 1),
            "fuel_percent": round((after / max_range) * 100, 1) if max_range else 0.0,
            "event": "stop_refuel",
            "gallons": round(s["gallons"], 2),
            "cost": round(s["cost"], 2),
            "label": f"Refuel +{round(s['gallons'], 1)} gal (${round(s['cost'], 2)})"
        })
        last_mile = s_mile
        last_fuel = after

    final_fuel = max(0.0, last_fuel - (total_miles - last_mile))
    timeline.append({
        "mile": round(total_miles, 1),
        "fuel_miles": round(final_fuel, 1),
        "fuel_percent": round((final_fuel / max_range) * 100, 1) if max_range else 0.0,
        "event": "finish",
        "label": "Destination Arrival"
    })
    return timeline
