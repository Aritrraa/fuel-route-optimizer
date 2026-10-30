import json
import time
from unittest import mock

import numpy as np
from django.core.cache import cache
from django.test import TestCase

from routing.models import FuelStation
from routing.services import geo, optimizer
from routing.services.optimizer import Candidate

# Rough I-55/I-44/I-40 path Chicago -> Los Angeles (lng, lat), densified.
WAYPOINTS = [(-87.62, 41.88), (-90.2, 38.63), (-97.5, 35.47), (-106.65, 35.08), (-111.65, 35.2), (-118.25, 34.05)]


def fake_route(start, finish):
    pts = []
    for (x1, y1), (x2, y2) in zip(WAYPOINTS, WAYPOINTS[1:]):
        for t in np.linspace(0, 1, 200, endpoint=False):
            pts.append([x1 + (x2 - x1) * t, y1 + (y2 - y1) * t])
    pts.append(list(WAYPOINTS[-1]))
    return pts, float(geo.cumulative_miles(pts)[-1]) * 1.1


class OptimizerTests(TestCase):
    def test_short_trip_needs_no_stop(self):
        self.assertEqual(optimizer.plan([Candidate(100, 3.0)], 300), [])

    def test_buys_only_what_is_needed_at_cheaper_station(self):
        # 800 mi trip, start full(500). Cheapest in range is mile 400 @ 3.0
        c = [Candidate(400, 3.0, "a"), Candidate(450, 4.0, "b")]
        stops = optimizer.plan(c, 800)
        self.assertEqual([s["station"] for s in stops], ["a"])
        # 400 mi left to drive, 100 mi of fuel left -> buy 300 mi = 30 gal @ 3.0
        self.assertAlmostEqual(stops[0]["gallons"], 30)
        self.assertAlmostEqual(stops[0]["cost"], 90)

    def test_fills_up_when_nothing_cheaper_ahead(self):
        c = [Candidate(300, 3.0, "a"), Candidate(700, 3.5, "b")]
        stops = optimizer.plan(c, 1100)
        self.assertEqual([s["station"] for s in stops], ["a", "b"])
        self.assertAlmostEqual(stops[0]["gallons"], 30)  # arrives 200 left, fill to 500
        self.assertAlmostEqual(stops[1]["gallons"], 30)  # 100 mi on board, 400 to go -> buy 300 mi

    def test_infeasible(self):
        with self.assertRaises(optimizer.InfeasibleRoute):
            optimizer.plan([Candidate(100, 3.0)], 1500)


class ApiTests(TestCase):
    def setUp(self):
        cache.clear()
        # Stations along the fake route every ~150 miles with varied prices.
        route, _ = fake_route(None, None)
        for i, k in enumerate(range(0, len(route), 100)):
            lng, lat = route[k]
            FuelStation.objects.create(opis_id=i, name=f"S{i}", city="X", state="OK",
                                       price=3 + (i % 4) * 0.25, lat=lat, lng=lng)

    @mock.patch("routing.services.routing_client.fetch_route", side_effect=fake_route)
    def test_route_endpoint(self, m):
        t = time.time()
        r = self.client.get("/api/route/", {"start": "Chicago, IL", "finish": "Los Angeles, CA"})
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertGreater(len(d["fuel_stops"]), 2)
        self.assertEqual(d["map"]["type"], "FeatureCollection")
        self.assertAlmostEqual(d["total_fuel_cost"], sum(s["cost"] for s in d["fuel_stops"]), places=1)
        miles = [s["mile_marker"] for s in d["fuel_stops"]]
        self.assertEqual(miles, sorted(miles))
        # never more than 500 miles between stops
        gaps = np.diff([0] + miles)
        self.assertLessEqual(max(gaps), 500.1)
        self.assertEqual(m.call_count, 1)
        # second identical request is served from cache: no extra routing call
        self.client.get("/api/route/", {"start": "Chicago, IL", "finish": "Los Angeles, CA"})
        self.assertEqual(m.call_count, 1)
        self.assertLess(time.time() - t, 3)

    def test_validation(self):
        self.assertEqual(self.client.get("/api/route/").status_code, 400)
        r = self.client.get("/api/route/", {"start": "Nowhereville, ZZ", "finish": "Chicago, IL"})
        self.assertEqual(r.status_code, 400)

    @mock.patch("routing.services.routing_client.fetch_route", side_effect=fake_route)
    def test_post_json(self, m):
        r = self.client.post("/api/route/", json.dumps({"start": "41.88,-87.62", "finish": "34.05,-118.25"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)

    @mock.patch("routing.services.routing_client.fetch_route", side_effect=fake_route)
    def test_custom_vehicle_parameters_and_timeline(self, m):
        r = self.client.get("/api/route/", {
            "start": "Chicago, IL",
            "finish": "Los Angeles, CA",
            "range_miles": 400,
            "mpg": 15,
            "corridor_miles": 8
        })
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["vehicle"]["range_miles"], 400)
        self.assertEqual(d["vehicle"]["mpg"], 15)
        self.assertEqual(d["vehicle"]["corridor_miles"], 8)
        self.assertIn("savings", d)
        self.assertIn("journey_timeline", d)
        self.assertGreater(len(d["journey_timeline"]), 1)
        # Check timeline event sequence
        self.assertEqual(d["journey_timeline"][0]["event"], "start")
        self.assertEqual(d["journey_timeline"][-1]["event"], "finish")

    def test_parameter_validation_bounds(self):
        r = self.client.get("/api/route/", {"start": "Chicago, IL", "finish": "Los Angeles, CA", "range_miles": 10})
        self.assertEqual(r.status_code, 400)
        self.assertIn("range_miles", r.json()["error"])
