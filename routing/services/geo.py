import re

import numpy as np

from . import cities

EARTH_MILES = 3958.8


def parse_location(text: str):
    """'lat,lng' or 'City, ST' (resolved offline). Returns (lat, lng, label) or raises ValueError."""
    text = (text or "").strip()
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", text)
    if m:
        lat, lng = float(m[1]), float(m[2])
        if not (24 <= lat <= 50 and -125 <= lng <= -66):
            raise ValueError(f"'{text}' is outside the continental USA")
        return lat, lng, text
    m = re.fullmatch(r"(.+?)\s*,\s*([A-Za-z]{2})", text)
    if not m:
        raise ValueError(f"Could not parse '{text}'. Use 'City, ST' or 'lat,lng'.")
    pt = cities.lookup(m[1], m[2])
    if not pt:
        raise ValueError(f"Unknown US city '{text}'")
    return pt[0], pt[1], f"{m[1].strip().title()}, {m[2].upper()}"


def cumulative_miles(coords):
    """coords: [[lng, lat], ...] -> numpy array of miles from start at each vertex."""
    a = np.radians(np.asarray(coords, dtype=float))
    lng, lat = a[:, 0], a[:, 1]
    dlat, dlng = np.diff(lat), np.diff(lng)
    h = np.sin(dlat / 2) ** 2 + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.sin(dlng / 2) ** 2
    seg = 2 * EARTH_MILES * np.arcsin(np.sqrt(h))
    return np.concatenate([[0.0], np.cumsum(seg)])


def snap_to_route(coords, stations, max_miles, chunk=400):
    """For each (lat, lng) find nearest route segment and fractional mile marker.
    Returns (segment_index, distance_miles, fractional_t) arrays.
    """
    if not len(coords) or not len(stations):
        return np.array([], dtype=int), np.array([]), np.array([])

    route = np.radians(np.asarray(coords, dtype=float)[:, ::-1])  # (N, 2): lat, lng
    pts = np.radians(np.asarray(stations, dtype=float).reshape(-1, 2))  # (M, 2): lat, lng
    num_pts = len(pts)
    num_route = len(route)

    idx = np.empty(num_pts, dtype=int)
    dist = np.empty(num_pts)
    frac_t = np.zeros(num_pts)

    rlat, rlng = route[:, 0], route[:, 1]

    for i in range(0, num_pts, chunk):
        p = pts[i:i + chunk]
        # Equirectangular approximation for fast local distance
        dlat = p[:, 0:1] - rlat[None, :]
        dlng = (p[:, 1:2] - rlng[None, :]) * np.cos(p[:, 0:1])
        d2 = dlat ** 2 + dlng ** 2
        nearest_v = d2.argmin(axis=1)

        # Refine by projecting onto adjacent road segments (j-1, j) and (j, j+1)
        chunk_idx = np.empty(len(p), dtype=int)
        chunk_dist = np.empty(len(p))
        chunk_t = np.zeros(len(p))

        for k, j in enumerate(nearest_v):
            best_d2 = d2[k, j]
            best_seg = j
            best_t = 0.0

            # Candidate segments connected to vertex j
            candidate_segs = []
            if j > 0:
                candidate_segs.append(j - 1)
            if j < num_route - 1:
                candidate_segs.append(j)

            pk_lat, pk_lng = p[k, 0], p[k, 1]
            cos_lat = np.cos(pk_lat)

            for seg_idx in candidate_segs:
                a_lat, a_lng = route[seg_idx, 0], route[seg_idx, 1]
                b_lat, b_lng = route[seg_idx + 1, 0], route[seg_idx + 1, 1]

                # Segment vector A -> B in equirectangular projection
                v_y = b_lat - a_lat
                v_x = (b_lng - a_lng) * cos_lat
                seg_len2 = v_y * v_y + v_x * v_x

                if seg_len2 > 1e-12:
                    w_y = pk_lat - a_lat
                    w_x = (pk_lng - a_lng) * cos_lat
                    t = max(0.0, min(1.0, (w_y * v_y + w_x * v_x) / seg_len2))
                    proj_y = a_lat + t * v_y
                    proj_x = a_lng + t * (b_lng - a_lng)
                    dy = pk_lat - proj_y
                    dx = (pk_lng - proj_x) * cos_lat
                    seg_d2 = dy * dy + dx * dx
                    if seg_d2 < best_d2:
                        best_d2 = seg_d2
                        best_seg = seg_idx
                        best_t = t

            chunk_idx[k] = best_seg
            chunk_dist[k] = np.sqrt(best_d2) * EARTH_MILES
            chunk_t[k] = best_t

        idx[i:i + chunk] = chunk_idx
        dist[i:i + chunk] = chunk_dist
        frac_t[i:i + chunk] = chunk_t

    return idx, dist, frac_t
