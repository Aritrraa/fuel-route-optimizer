import math
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import models

from routing.models import FuelStation
from . import geo, optimizer, routing_client


def _route(start, finish):
    key = f"route:{start[0]:.3f},{start[1]:.3f}:{finish[0]:.3f},{finish[1]:.3f}"
    hit = cache.get(key)
    if hit:
        return hit, True
    result = routing_client.fetch_route(start, finish)
    cache.set(key, result, 60 * 60 * 24)
    return result, False


def build_plan(start_text, finish_text, range_miles=None, mpg=None, corridor_miles=None):
    range_miles = float(range_miles) if range_miles is not None else float(settings.VEHICLE_RANGE_MILES)
    mpg = float(mpg) if mpg is not None else float(settings.VEHICLE_MPG)
    corridor = float(corridor_miles) if corridor_miles is not None else float(settings.CORRIDOR_MILES)

    s_lat, s_lng, s_label = geo.parse_location(start_text)
    f_lat, f_lng, f_label = geo.parse_location(finish_text)
    (coords, miles), cached = _route((s_lat, s_lng), (f_lat, f_lng))

    # Segmented bounding box prefilter in SQL to avoid fetching the entire continent on diagonal routes
    dlat = corridor / 69.0
    chunk_size = 50
    q_filter = models.Q()
    for k in range(0, len(coords), chunk_size):
        chunk = coords[k:k + chunk_size + 1]
        c_lngs = [c[0] for c in chunk]
        c_lats = [c[1] for c in chunk]
        avg_lat = sum(c_lats) / len(c_lats)
        chunk_dlng = corridor / (69.0 * math.cos(math.radians(avg_lat)))
        q_filter |= models.Q(
            lat__range=(min(c_lats) - dlat, max(c_lats) + dlat),
            lng__range=(min(c_lngs) - chunk_dlng, max(c_lngs) + chunk_dlng)
        )

    qs = list(FuelStation.objects.filter(q_filter).distinct())

    idx, dist, frac_t = geo.snap_to_route(coords, [(s.lat, s.lng) for s in qs], corridor)
    cum = geo.cumulative_miles(coords)
    scale = miles / cum[-1] if cum[-1] else 1.0  # align haversine miles to routed miles

    cands = []
    for st, i, d, t in zip(qs, idx, dist, frac_t):
        if d <= corridor:
            seg_start = cum[i]
            seg_end = cum[min(i + 1, len(cum) - 1)]
            station_mile = (seg_start + t * (seg_end - seg_start)) * scale
            cands.append(optimizer.Candidate(float(station_mile), float(st.price), (st, float(d))))

    stops = optimizer.plan(cands, miles, max_range=range_miles, mpg=mpg)
    total = sum(s["cost"] for s in stops)
    gallons = sum(s["gallons"] for s in stops)

    # Benchmark statistics (route average, min, max price vs optimized)
    corridor_prices = [c.price for c in cands]
    if corridor_prices:
        corridor_avg_price = sum(corridor_prices) / len(corridor_prices)
        corridor_min_price = min(corridor_prices)
        corridor_max_price = max(corridor_prices)
    else:
        corridor_avg_price = corridor_min_price = corridor_max_price = 0.0

    avg_price_paid = (total / gallons) if gallons > 0 else 0.0
    savings_vs_avg = max(0.0, (corridor_avg_price * gallons) - total) if gallons > 0 else 0.0
    savings_vs_max = max(0.0, (corridor_max_price * gallons) - total) if gallons > 0 else 0.0

    features = [{"type": "Feature", "properties": {"kind": "route", "distance_miles": round(miles, 1)},
                 "geometry": {"type": "LineString", "coordinates": coords}},
                {"type": "Feature", "properties": {"kind": "start", "label": s_label},
                 "geometry": {"type": "Point", "coordinates": [s_lng, s_lat]}},
                {"type": "Feature", "properties": {"kind": "finish", "label": f_label},
                 "geometry": {"type": "Point", "coordinates": [f_lng, f_lat]}}]
    out_stops = []
    for n, s in enumerate(stops, 1):
        st, off = s["station"]
        info = {
            "stop": n,
            "name": st.name,
            "address": st.address,
            "city": st.city,
            "state": st.state,
            "price_per_gallon": round(s["price"], 3),
            "gallons": round(s["gallons"], 2),
            "cost": round(s["cost"], 2),
            "mile_marker": round(s["mile"], 1),
            "miles_off_route": round(off, 1),
            "range_before_miles": round(s.get("range_before_miles", 0.0), 1),
            "range_after_miles": round(s.get("range_after_miles", 0.0), 1),
            "lat": st.lat,
            "lng": st.lng,
        }
        out_stops.append(info)
        features.append({"type": "Feature", "properties": {"kind": "fuel_stop", **info},
                         "geometry": {"type": "Point", "coordinates": [st.lng, st.lat]}})

    timeline = optimizer.build_journey_timeline(out_stops, miles, max_range=range_miles, mpg=mpg)

    return {
        "start": s_label, "finish": f_label,
        "total_distance_miles": round(miles, 1),
        "vehicle": {
            "range_miles": round(range_miles, 1),
            "mpg": round(mpg, 1),
            "corridor_miles": round(corridor, 1),
            "assumption": "Tank is full at the start; only fuel bought en route is billed."
        },
        "fuel_stops": out_stops,
        "total_gallons_purchased": round(gallons, 2),
        "total_fuel_cost": round(total, 2),
        "route_cached": cached,
        "savings": {
            "average_price_paid": round(avg_price_paid, 3),
            "corridor_avg_price": round(corridor_avg_price, 3),
            "corridor_min_price": round(corridor_min_price, 3),
            "corridor_max_price": round(corridor_max_price, 3),
            "savings_vs_corridor_avg": round(savings_vs_avg, 2),
            "savings_vs_corridor_max": round(savings_vs_max, 2)
        },
        "journey_timeline": timeline,
        "map": {"type": "FeatureCollection", "features": features},
    }
