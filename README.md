# fleet-router

A vehicle-routing-problem (VRP) optimizer for a scrap-yard fleet that compares a greedy baseline against a Google OR-Tools solver and reports the operating-cost savings.

## Overview

fleet-router assigns pickup jobs to trucks and orders the stops on each route under real fleet constraints: per-truck capacity and a maximum route time. It builds two plans for the same trucks and jobs:

1. A greedy nearest-neighbor baseline, the kind of plan a dispatcher might produce by hand.
2. An OR-Tools VRP plan that minimizes the exact operating cost.

It then prices both plans with the same cost model and reports the difference as daily, monthly, and annual savings. The optimized routes are drawn on a Leaflet map in the frontend.

The backend is FastAPI. State lives in an in-memory store that is seeded with demo trucks and jobs on startup.

## How it works

### Greedy baseline

The baseline (`app/engine/core.py`, `compute_baseline`) walks trucks in order. For each truck it starts at the depot and repeatedly picks the nearest unassigned job that is still feasible:

- The job must fit the truck's remaining capacity.
- Adding the job (travel to it, service at it, and travel back to the depot) must not push the route past the max route time.

When no feasible job remains, the truck's route is closed and the next truck is filled. This is a fast, reasonable heuristic, but it is greedy and not cost-aware, so it leaves savings on the table.

### OR-Tools VRP solver

The optimized plan (`_build_routes_with_ortools`) builds a Google OR-Tools `RoutingModel`:

- A single shared depot (the first truck's start location) is node 0; each job is a node.
- A Time dimension bounds each route by the max route time (travel time plus service time at each stop).
- A Capacity dimension enforces each truck's capacity (demand is scaled to integer units internally).
- The arc cost evaluator is the operating cost of each leg (see cost model below), so the solver minimizes total cost rather than just distance.

The first solution uses PATH_CHEAPEST_ARC, then GUIDED_LOCAL_SEARCH refines it. The solver runs under a 5-second time limit.

### Cost model

Distances are great-circle (haversine) kilometers. Travel time is derived from distance at an assumed average truck speed (40 km/h). The cost model (all values in `app/engine/core.py`) is:

- Fuel: $0.40 per km
- Maintenance: $0.12 per km
- Driver labor: $40.00 per hour, applied to total driver-minutes across all trucks

For each arc the solver minimizes `distance_km * (fuel + maintenance) + time_minutes * (labor / 60)`, where time includes both travel and the service time at the destination.

### Constraints

- Per-truck capacity (tons).
- Maximum route time per truck (default 10 hours), enforced in both the baseline and the OR-Tools model.

Before the solver runs, a quick feasibility check rejects obviously impossible inputs (no trucks, no jobs, total demand over total capacity, or total service time over the total driver-time budget) and returns a structured HTTP 400 with diagnostics.

### Savings calculation

Both plans are priced with the same fuel, maintenance, and labor model. The cost difference is the daily savings. Monthly and annual figures extrapolate using 22 working days per month and 260 per year. The optimize response returns the per-component costs for both plans plus the savings totals.

### Map visualization

The React frontend (`frontend/src/RouteMap.tsx`) fetches trucks and jobs, calls `/optimize`, and draws each truck's optimized route as a polyline on a Leaflet map with stop markers.

## Tech stack

- Backend: Python, FastAPI, Google OR-Tools (constraint-solver routing), Pydantic, Uvicorn
- Frontend: React, Vite, TypeScript, Leaflet (react-leaflet)

## Setup

### Backend

From the project root:

```
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

The API serves on http://127.0.0.1:8000 and seeds demo data on startup.

### Frontend

```
cd frontend
npm install
npm run dev
```

Vite serves the UI on http://localhost:5173.

## Usage

### API endpoints

- `GET /ping` health check, returns `{"status": "ok"}`.
- `GET /trucks` current list of trucks in the yard.
- `GET /jobs` current list of jobs (stops).
- `POST /optimize` runs the baseline and OR-Tools optimization on the current state and returns the optimized routes plus the full cost breakdown and savings.
- `POST /demo/reset` clears the in-memory store and repopulates it with fresh random demo data.

### Map UI

Run both servers, open the Vite URL, and the map loads the seeded trucks and jobs, runs an optimization, and draws each truck's route. Use the demo reset to regenerate the scenario.

## Project structure

```
.
├── app/
│   ├── main.py            # FastAPI app, routes, CORS, startup seeding
│   ├── services.py        # service layer between routes and engine/store
│   ├── optimizer.py       # optimization orchestration
│   ├── engine/
│   │   └── core.py        # stateless VRP engine: baseline, OR-Tools model, cost model
│   ├── schemas.py         # Pydantic models (Truck, Job, OptimizeResult, ...)
│   ├── store.py           # in-memory store
│   ├── repositories.py    # repository interfaces
│   ├── repositories_impl.py
│   └── sample_data.py     # demo trucks/jobs
├── frontend/
│   └── src/
│       └── RouteMap.tsx   # Leaflet map + optimize call
├── requirements.txt
├── .env.example
└── .gitignore
```

## Limitations

- State is held in an in-memory store only. There is no database and nothing persists across restarts.
- No authentication or multi-tenancy.
- Trucks and jobs are demo data seeded at startup; there are no create/update/delete endpoints.
- The OR-Tools solver is capped at a 5-second time limit, so large instances return the best plan found within that window rather than a proven optimum.
- The cost model uses fixed rates and a single assumed average speed; it does not model traffic, time windows, or overtime.

## Configuration

`ORS_API_KEY` (OpenRouteService) appears in the local `.env` but is not referenced anywhere in the backend code. It is legacy/optional and not required to run the app, which uses haversine distances. See `.env.example`.
