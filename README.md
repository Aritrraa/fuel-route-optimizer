# Fuel Route Optimizer API — Spotter Backend Assessment

[![Django](https://img.shields.io/badge/Django-6.1.2-092E20?style=flat&logo=django)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.13-3776AB?style=flat&logo=python)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat&logo=docker)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-9%2F9%20Passing-brightgreen?style=flat)]()
[![License](https://img.shields.io/badge/License-MIT-blue.svg)]()

A high-performance highway route and fuel cost optimizer built with **Django 6.1**. Given a start and destination within the continental USA, it computes the driving route (GeoJSON), identifies candidate fuel stops along a 5-mile highway corridor, and determines the mathematically optimal (cheapest) refueling stops adhering to vehicle constraints (500-mile tank range, 10 MPG), returning total fuel expenditure and an interactive Leaflet map.

---

## 🚀 Key Requirements & Technical Highlights

| Requirement | Implementation & Architectural Decision |
| :--- | :--- |
| **Django Framework** | Built on **Django 6.1.2** with clean modular service architecture. |
| **Strict Minimal External Calls** | **Exactly 1 external routing call per route** (OSRM / OpenRouteService). City geocoding is performed **100% offline** using a local pre-indexed dictionary of US cities, avoiding API latency and rate limits. |
| **High Performance** | **Segmented SQL Bounding Boxes** + **NumPy Point-to-Segment Projections** snap candidate stations in milliseconds without loading the entire continent. |
| **Mathematical Optimality** | Solves the **Gas Station Problem** via a provably optimal greedy algorithm: buys only what is needed to reach cheaper fuel ahead, or fills to capacity if current station is the local minimum. |
| **Zero Setup / Docker Ready** | One-command startup via `docker compose up --build`. |
| **Interactive UI & Postman** | Interactive Leaflet dashboard at `/` with real-time fuel tank journey visualization, plus a comprehensive Postman collection for demoing. |

---

## ⚡ Quickstart

### Option 1: Run with Docker (Recommended)
```bash
docker compose up --build
```
Open **[http://localhost:8000/](http://localhost:8000/)** in your browser.

---

### Option 2: Run Locally (Python 3.12+)
```bash
# 1. Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Apply database migrations
python manage.py migrate

# 4. Import and geocode fuel stations (runs once)
python manage.py import_stations

# 5. Start development server
python manage.py runserver
```
Visit **[http://localhost:8000/](http://localhost:8000/)**.

---

## 📡 API Usage & Endpoints

### 1. Plan Route (`GET /api/route/`)
```bash
curl "http://localhost:8000/api/route/?start=Chicago,%20IL&finish=Los%20Angeles,%20CA"
```

### 2. Plan Route (`POST /api/route/`)
```bash
curl -X POST http://localhost:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{
    "start": "New York, NY",
    "finish": "Miami, FL"
  }'
```

### 3. Optional Vehicle Parameters
The API supports custom vehicle parameters across both GET and POST:
- `range_miles` (float, default: `500`): Maximum vehicle range on a full tank.
- `mpg` (float, default: `10`): Miles per gallon.
- `corridor_miles` (float, default: `5`): Maximum search distance off the highway line.

Example:
```bash
curl "http://localhost:8000/api/route/?start=Seattle,%20WA&finish=San%20Diego,%20CA&range_miles=400&mpg=12&corridor_miles=8"
```

---

### Sample JSON Response
```json
{
  "start": "Chicago, IL",
  "finish": "Los Angeles, CA",
  "total_distance_miles": 2024.4,
  "vehicle": {
    "range_miles": 500.0,
    "mpg": 10.0,
    "corridor_miles": 5.0,
    "assumption": "Tank is full at the start; only fuel bought en route is billed."
  },
  "fuel_stops": [
    {
      "stop": 1,
      "name": "KUM & GO #0370",
      "address": "I-80, EXIT 439 & SR-370",
      "city": "Gretna",
      "state": "NE",
      "price_per_gallon": 2.921,
      "gallons": 7.79,
      "cost": 22.75,
      "mile_marker": 485.3,
      "miles_off_route": 1.9,
      "range_before_miles": 14.7,
      "range_after_miles": 92.6,
      "lat": 41.134458,
      "lng": -96.245837
    }
  ],
  "total_gallons_purchased": 152.44,
  "total_fuel_cost": 468.65,
  "savings": {
    "average_price_paid": 3.074,
    "corridor_avg_price": 3.412,
    "savings_vs_corridor_avg": 51.44
  },
  "journey_timeline": [
    { "mile": 0.0, "fuel_miles": 500.0, "event": "start", "label": "Trip Start (Full Tank)" },
    { "mile": 485.3, "fuel_miles": 14.7, "event": "stop_arrival", "label": "Arrive at Stop #1" }
  ],
  "map": {
    "type": "FeatureCollection",
    "features": [...]
  }
}
```

---

## 🏛️ System Architecture

```
fuelroute/
├── config/                         # Django configuration & settings
│   ├── settings.py                 # Environment-aware settings & vehicle defaults
│   ├── urls.py                     # URL routing
├── data/
│   ├── fuel-prices-for-be-assessment.csv  # Raw OPIS fuel station dataset
│   └── us_cities.csv               # Offline US city coordinates index
├── routing/                        # Core application
│   ├── management/commands/
│   │   └── import_stations.py      # Cleans, deduplicates, and geocodes stations
│   ├── services/                   # Modular domain service layer
│   │   ├── cities.py               # In-memory LRU-cached offline city lookup
│   │   ├── geo.py                  # Point-to-segment projection & Haversine math
│   │   ├── optimizer.py            # Greedy Gas Station optimization solver
│   │   ├── planner.py              # Pipeline orchestrator & segmented bounding box search
│   │   └── routing_client.py       # Single-call routing client with retry resilience
│   ├── templates/routing/
│   │   └── index.html              # Leaflet UI & fuel tank timeline visualizer
│   ├── tests.py                    # Comprehensive test suite
│   ├── urls.py                     # Route endpoints
│   └── views.py                    # API controllers & parameter validation
├── Dockerfile                      # Production container image
├── docker-compose.yml              # One-command orchestration
├── openapi.yaml                    # OpenAPI 3.0 specification
├── postman_collection.json         # Postman collection for live demo
└── requirements.txt
```

---

## 🧪 Testing

Execute the automated test suite with full verbosity:
```bash
python manage.py test routing -v 2
```
Covers:
- Optimizer logic (short routes, zero-fill trips, cheaper station ahead, infeasibility exceptions).
- API integration endpoints (GET query params, POST JSON bodies, coordinate parsing).
- Route caching (verifying zero redundant outbound HTTP calls).
- Custom vehicle parameter validation and boundary enforcement.
- Journey timeline sequence and cost benchmarking.

---

## 🎥 5-Minute Loom Video Guide (For Interview Submission)

Here is a recommended script for recording the requested 5-minute Loom video:

1. **Introduction (0:00 - 0:45)**:
   - Introduce yourself: *"Hi, I'm Aritra. This is my submission for the Backend Django Engineer role at Spotter."*
   - State the core challenge: Computing the driving route and identifying optimal fuel stops along a 500-mile vehicle range constraint.
2. **Postman API Demonstration (0:45 - 2:15)**:
   - Open Postman with the provided `postman_collection.json`.
   - Run **Request 1 (Chicago to Los Angeles)**: Show distance (2,024 mi), fuel stops chosen, total cost ($468.65), and GeoJSON map object.
   - Run **Request 4 (Custom Range & MPG)**: Show how passing `range_miles=400&mpg=12` adapts stop selections dynamically.
   - Run **Request 5 (Short Trip)**: Demonstrate that a 300-mile trip requires 0 stops because the vehicle starts with a full tank.
3. **Architecture & Codebase Walkthrough (2:15 - 4:15)**:
   - **Offline Geocoding (`cities.py`)**: Explain how city coordinates are resolved offline from `us_cities.csv` to ensure **strictly 1 external API call**.
   - **Segmented Spatial Filtering (`planner.py` & `geo.py`)**: Explain how the route is partitioned into segmented bounding boxes in SQL, followed by vectorized point-to-segment snapping using NumPy.
   - **Optimizer (`optimizer.py`)**: Explain the greedy choice property—buying just enough to reach a cheaper station ahead, or filling to capacity when at a local price minimum.
4. **Interactive UI & Closing (4:15 - 5:00)**:
   - Switch to browser (`http://localhost:8000/`) for 30 seconds to show the Leaflet map, custom stop badges with prices, and the visual fuel tank journey chart.
   - Close with: *"Thank you for your time, and I look forward to discussing this in the next round!"*
