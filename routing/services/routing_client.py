"""Single-call route fetch. Returns GeoJSON-style [lng, lat] coords + miles."""
import time
import requests
from django.conf import settings

METERS_PER_MILE = 1609.344


class RoutingError(Exception):
    pass


def fetch_route(start, finish):
    """start/finish are (lat, lng). Exactly ONE external route query with retry resilience."""
    headers = {"User-Agent": "FuelRoutePlanner/2.0 (Assessment Evaluation)"}
    last_exc = None

    for attempt in range(2):
        try:
            if settings.ORS_API_KEY:
                r = requests.post(
                    "https://api.openrouteservice.org/v2/directions/driving-car/geojson",
                    json={"coordinates": [[start[1], start[0]], [finish[1], finish[0]]]},
                    headers={"Authorization": settings.ORS_API_KEY, **headers},
                    timeout=settings.ROUTING_TIMEOUT,
                )
                r.raise_for_status()
                feat = r.json()["features"][0]
                return feat["geometry"]["coordinates"], feat["properties"]["summary"]["distance"] / METERS_PER_MILE

            url = (
                f"{settings.OSRM_URL}/route/v1/driving/{start[1]},{start[0]};{finish[1]},{finish[0]}"
                "?overview=full&geometries=geojson"
            )
            r = requests.get(url, headers=headers, timeout=settings.ROUTING_TIMEOUT)
            r.raise_for_status()
            route = r.json()["routes"][0]
            return route["geometry"]["coordinates"], route["distance"] / METERS_PER_MILE
        except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(1.0)

    raise RoutingError(f"Routing service failed after retries: {last_exc}") from last_exc
