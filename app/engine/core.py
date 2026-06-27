# app/engine/core.py
"""
Standalone optimization engine for ScrapFlo.

This module is intentionally **stateless** and contains all of the
routing / VRP logic. It does NOT know about FastAPI or the in-memory
store – it only works with typed Truck / Job objects.

The FastAPI layer (app/main.py + app/optimizer.py) is responsible for:
- Fetching trucks / jobs from whatever storage layer we use.
- Passing them into `run_optimization`.
- Returning the Pydantic `OptimizeResult` to the client.

This keeps the engine portable and easy to unit-test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .. import schemas

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# Rough average truck speed (km/h) for estimating time
AVG_TRUCK_SPEED_KMH: float = 40.0

# Max route length per truck (minutes) – used by baseline *and* OR-Tools
MAX_ROUTE_MINUTES: int = 10 * 60  # 10 hours

# ----------------- COST MODEL (exactly minimized by OR-Tools) --------------

# Fuel + maintenance per km (USD)
FUEL_COST_PER_KM: float = 0.40          # e.g. ~$0.64 per mile
MAINTENANCE_COST_PER_KM: float = 0.12   # e.g. ~$0.19 per mile

# Driver labor per hour (USD)
DRIVER_COST_PER_HOUR: float = 40.0      # fully-loaded driver cost

# Derived rates
COST_PER_KM: float = FUEL_COST_PER_KM + MAINTENANCE_COST_PER_KM
COST_PER_MINUTE: float = DRIVER_COST_PER_HOUR / 60.0

# Working days for extrapolated savings
WORKING_DAYS_PER_MONTH: int = 22
WORKING_DAYS_PER_YEAR: int = 260


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Great-circle distance between two points in kilometers.
    """
    r = 6371.0  # km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def compute_leg_time_minutes(distance_km: float) -> float:
    """
    Convert a leg distance (km) into minutes using the average speed.
    """
    hours = distance_km / AVG_TRUCK_SPEED_KMH
    return hours * 60.0


# ---------------------------------------------------------------------------
# Internal dataclasses for engine representation
# ---------------------------------------------------------------------------


@dataclass
class EngineTruck:
    id: int
    name: str
    capacity_tons: float
    start_lat: float
    start_lng: float


@dataclass
class EngineJob:
    id: int
    customer_name: str
    lat: float
    lng: float
    demand_tons: float
    service_minutes: float


# ---------------------------------------------------------------------------
# Greedy baseline heuristic
# ---------------------------------------------------------------------------


def _build_engine_trucks(trucks: List[schemas.Truck]) -> List[EngineTruck]:
    return [
        EngineTruck(
            id=t.id,
            name=t.name,
            capacity_tons=float(t.capacity_tons),
            start_lat=float(t.start_lat),
            start_lng=float(t.start_lng),
        )
        for t in trucks
    ]


def _build_engine_jobs(jobs: List[schemas.Job]) -> List[EngineJob]:
    return [
        EngineJob(
            id=j.id,
            customer_name=j.customer_name,
            lat=float(j.lat),
            lng=float(j.lng),
            demand_tons=float(j.demand_tons),
            service_minutes=float(j.service_minutes),
        )
        for j in jobs
    ]


def _compute_route_distance_and_time_for_order(
    truck: EngineTruck,
    ordered_jobs: List[EngineJob],
) -> Tuple[float, float]:
    """
    Given a fixed order of jobs, compute total travel distance (km) and
    total driver minutes, including:

      - depot -> first job (travel)
      - between jobs (travel)
      - service at each job
      - last job -> depot (travel)
    """
    if not ordered_jobs:
        return 0.0, 0.0

    total_distance_km = 0.0
    total_minutes = 0.0

    prev_lat = truck.start_lat
    prev_lng = truck.start_lng

    for job in ordered_jobs:
        leg_km = haversine_km(prev_lat, prev_lng, job.lat, job.lng)
        leg_minutes = compute_leg_time_minutes(leg_km)

        total_distance_km += leg_km
        total_minutes += leg_minutes
        total_minutes += job.service_minutes

        prev_lat = job.lat
        prev_lng = job.lng

    # Return to depot (travel only)
    leg_km = haversine_km(prev_lat, prev_lng, truck.start_lat, truck.start_lng)
    leg_minutes = compute_leg_time_minutes(leg_km)

    total_distance_km += leg_km
    total_minutes += leg_minutes

    return total_distance_km, total_minutes


def _greedy_assign_jobs_to_trucks(
    trucks: List[EngineTruck],
    jobs: List[EngineJob],
    max_route_minutes: float,
) -> Tuple[Dict[int, List[EngineJob]], float, float, float]:
    """
    Very simple greedy heuristic:
    - For each truck in order:
      - Start at the depot
      - Repeatedly pick the nearest feasible unassigned job:
        - Fits remaining capacity
        - Doesn't exceed max_route_minutes (including service + return to depot)
      - Stop when no feasible job remains for that truck.
    - Continue until we run out of trucks or jobs.

    Returns:
      routes_by_truck: mapping truck_id -> ordered list of jobs
      total_distance_km: aggregated distance across all trucks
      max_route_minutes: max single-truck route minutes
      total_driver_minutes: sum of all trucks' route minutes
    """
    remaining_jobs = jobs.copy()
    routes_by_truck: Dict[int, List[EngineJob]] = {}
    total_distance_km = 0.0
    max_used_minutes = 0.0
    total_driver_minutes = 0.0

    for truck in trucks:
        current_lat = truck.start_lat
        current_lng = truck.start_lng
        current_load = 0.0
        current_minutes = 0.0

        route: List[EngineJob] = []

        while remaining_jobs:
            # Find nearest feasible job
            best_job = None
            best_distance = None

            for job in remaining_jobs:
                # Capacity check
                if current_load + job.demand_tons > truck.capacity_tons:
                    continue

                # Time check:
                #   current -> job (travel)
                #   + service at job
                #   + job -> depot (travel)
                leg_to_job_km = haversine_km(current_lat, current_lng, job.lat, job.lng)
                leg_to_job_minutes = compute_leg_time_minutes(leg_to_job_km)

                leg_back_km = haversine_km(
                    job.lat, job.lng, truck.start_lat, truck.start_lng
                )
                leg_back_minutes = compute_leg_time_minutes(leg_back_km)

                projected_minutes = (
                    current_minutes
                    + leg_to_job_minutes
                    + job.service_minutes
                    + leg_back_minutes
                )

                if projected_minutes > max_route_minutes:
                    continue

                if best_distance is None or leg_to_job_km < best_distance:
                    best_distance = leg_to_job_km
                    best_job = job

            if best_job is None:
                break  # no feasible job for this truck

            # Assign job
            route.append(best_job)
            remaining_jobs.remove(best_job)

            # Update current state
            leg_km = haversine_km(
                current_lat, current_lng, best_job.lat, best_job.lng
            )
            leg_minutes = compute_leg_time_minutes(leg_km)

            current_minutes += leg_minutes + best_job.service_minutes
            current_load += best_job.demand_tons
            current_lat, current_lng = best_job.lat, best_job.lng

        if route:
            routes_by_truck[truck.id] = route
            route_distance_km, route_minutes = _compute_route_distance_and_time_for_order(
                truck, route
            )
            total_distance_km += route_distance_km
            max_used_minutes = max(max_used_minutes, route_minutes)
            total_driver_minutes += route_minutes

    return routes_by_truck, total_distance_km, max_used_minutes, total_driver_minutes


def compute_baseline(
    trucks: List[schemas.Truck],
    jobs: List[schemas.Job],
    max_route_minutes: float = float(MAX_ROUTE_MINUTES),
) -> Tuple[float, float, float, int]:
    """
    Compute a naive "baseline" solution using the greedy assignment heuristic.

    Returns:
      baseline_distance_km
      baseline_max_route_minutes   (longest driver's day)
      baseline_total_driver_minutes (sum across all trucks)
      baseline_trucks_used
    """
    if not trucks or not jobs:
        return 0.0, 0.0, 0.0, 0

    engine_trucks = _build_engine_trucks(trucks)
    engine_jobs = _build_engine_jobs(jobs)

    (
        routes_by_truck,
        total_distance_km,
        max_route_minutes_used,
        total_driver_minutes,
    ) = _greedy_assign_jobs_to_trucks(engine_trucks, engine_jobs, max_route_minutes)

    baseline_trucks_used = len(routes_by_truck)
    return total_distance_km, max_route_minutes_used, total_driver_minutes, baseline_trucks_used


# ---------------------------------------------------------------------------
# Quick infeasibility checks
# ---------------------------------------------------------------------------


class InfeasibleOptimizationError(Exception):
    """
    Raised when we can tell *quickly* that the optimization problem is impossible
    (e.g., total demand exceeds total capacity).
    """

    def __init__(self, message: str, diagnostics: Dict[str, float]) -> None:
        super().__init__(message)
        self.message = message
        self.diagnostics = diagnostics


def _quick_feasibility_check(
    trucks: List[schemas.Truck],
    jobs: List[schemas.Job],
    max_route_minutes: float,
) -> None:
    """
    Before calling OR-Tools, run some cheap checks so we can give the user
    a helpful explanation when the problem is obviously impossible.
    """
    if not trucks:
        raise InfeasibleOptimizationError(
            "No trucks available – please add at least one truck.",
            diagnostics={
                "total_demand_tons": float(sum(j.demand_tons for j in jobs)),
                "total_capacity_tons": 0.0,
            },
        )

    if not jobs:
        raise InfeasibleOptimizationError(
            "No jobs to optimize – please add at least one job.",
            diagnostics={
                "total_demand_tons": 0.0,
                "total_capacity_tons": float(sum(t.capacity_tons for t in trucks)),
            },
        )

    total_capacity = float(sum(t.capacity_tons for t in trucks))
    total_demand = float(sum(j.demand_tons for j in jobs))

    total_service_minutes = float(sum(j.service_minutes for j in jobs))
    total_time_budget_minutes = float(len(trucks) * max_route_minutes)

    diagnostics = {
        "total_demand_tons": total_demand,
        "total_capacity_tons": total_capacity,
        "total_service_minutes": total_service_minutes,
        "total_time_budget_minutes": total_time_budget_minutes,
    }

    if total_demand > total_capacity + 1e-6:
        raise InfeasibleOptimizationError(
            "Total container demand exceeds total truck capacity.",
            diagnostics=diagnostics,
        )

    if total_service_minutes > total_time_budget_minutes + 1e-6:
        raise InfeasibleOptimizationError(
            "Total service time requested exceeds total driver time budget.",
            diagnostics=diagnostics,
        )


# ---------------------------------------------------------------------------
# OR-Tools VRP model
# ---------------------------------------------------------------------------


def _build_ortools_data(
    trucks: List[schemas.Truck],
    jobs: List[schemas.Job],
) -> Dict:
    """
    Prepare input data for OR-Tools RoutingModel.
    """
    engine_trucks = _build_engine_trucks(trucks)
    engine_jobs = _build_engine_jobs(jobs)

    all_locations: List[Tuple[float, float]] = []
    all_demands: List[float] = []
    all_service: List[float] = []

    # Node 0 = depot (single shared depot, first truck's start)
    depot_lat = engine_trucks[0].start_lat
    depot_lng = engine_trucks[0].start_lng

    all_locations.append((depot_lat, depot_lng))
    all_demands.append(0.0)
    all_service.append(0.0)

    job_index_to_engine: Dict[int, EngineJob] = {}
    for idx, job in enumerate(engine_jobs, start=1):
        all_locations.append((job.lat, job.lng))
        all_demands.append(job.demand_tons)
        all_service.append(job.service_minutes)
        job_index_to_engine[idx] = job

    vehicle_capacities = [float(t.capacity_tons) for t in engine_trucks]

    return {
        "locations": all_locations,
        "demands": all_demands,
        "service_minutes": all_service,
        "num_vehicles": len(engine_trucks),
        "vehicle_capacities": vehicle_capacities,
        "depot_index": 0,
        "engine_trucks": engine_trucks,
        "job_index_to_engine": job_index_to_engine,
    }


def _build_routes_with_ortools(
    trucks: List[schemas.Truck],
    jobs: List[schemas.Job],
    max_route_minutes: float,
) -> Tuple[List[schemas.OptimizedTruckRoute], float, int, float, int]:
    """
    Use OR-Tools RoutingModel to build optimized routes.

    Objective:
      Minimize exact operating cost under the linear model:

        cost_per_km = FUEL_COST_PER_KM + MAINTENANCE_COST_PER_KM
        cost_per_minute = DRIVER_COST_PER_HOUR / 60

      For each arc i -> j:

        dist_km  = Haversine(i, j)
        travel   = compute_leg_time_minutes(dist_km)
        service  = service_minutes[j]   (0 for depot)
        time_min = travel + service

        arc_cost = dist_km * cost_per_km + time_min * cost_per_minute

    Returns:
      - list of OptimizedTruckRoute
      - total_distance_km
      - max_route_minutes
      - total_driver_minutes (sum over all trucks)
      - optimized_trucks_used
    """
    if not trucks or not jobs:
        return [], 0.0, 0, 0.0, 0

    data = _build_ortools_data(trucks, jobs)

    manager = pywrapcp.RoutingIndexManager(
        len(data["locations"]), data["num_vehicles"], data["depot_index"]
    )
    routing = pywrapcp.RoutingModel(manager)

    # --- 1) Time callback (travel + service at destination) for Time dimension ---

    def time_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)

        lat1, lng1 = data["locations"][from_node]
        lat2, lng2 = data["locations"][to_node]

        dist_km = haversine_km(lat1, lng1, lat2, lng2)
        travel_min = compute_leg_time_minutes(dist_km)
        service_min = float(data["service_minutes"][to_node])
        total_min = travel_min + service_min
        return int(round(total_min))

    time_callback_index = routing.RegisterTransitCallback(time_callback)

    routing.AddDimension(
        time_callback_index,
        0,  # no slack
        int(max_route_minutes),
        True,
        "Time",
    )

    time_dimension = routing.GetDimensionOrDie("Time")  # noqa: F841

    # --- 2) Capacity dimension (unchanged) ---

    def demand_callback(from_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        return int(round(data["demands"][from_node] * 1000))

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)

    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        [int(round(cap * 1000)) for cap in data["vehicle_capacities"]],
        True,
        "Capacity",
    )

    # --- 3) Cost callback (objective) ---

    def cost_callback(from_index: int, to_index: int) -> int:
        """
        Return arc cost in *cents* for OR-Tools:

          arc_cost_usd =
              dist_km * COST_PER_KM
            + time_min * COST_PER_MINUTE
        """
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)

        lat1, lng1 = data["locations"][from_node]
        lat2, lng2 = data["locations"][to_node]

        dist_km = haversine_km(lat1, lng1, lat2, lng2)
        travel_min = compute_leg_time_minutes(dist_km)
        service_min = float(data["service_minutes"][to_node])
        time_min = travel_min + service_min

        arc_cost_usd = dist_km * COST_PER_KM + time_min * COST_PER_MINUTE
        return int(round(arc_cost_usd * 100.0))  # cents

    cost_callback_index = routing.RegisterTransitCallback(cost_callback)

    routing.SetArcCostEvaluatorOfAllVehicles(cost_callback_index)

    # --- 4) Solver parameters ---

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 5

    solution = routing.SolveWithParameters(search_parameters)

    if solution is None:
        raise InfeasibleOptimizationError(
            "No feasible route found by OR-Tools.",
            diagnostics={
                "total_demand_tons": float(sum(j.demand_tons for j in jobs)),
                "total_capacity_tons": float(sum(t.capacity_tons for t in trucks)),
            },
        )

    # --- 5) Extract routes ---

    optimized_routes: List[schemas.OptimizedTruckRoute] = []
    total_distance_km = 0.0
    max_route_minutes = 0
    total_driver_minutes = 0.0
    optimized_trucks_used = 0

    engine_trucks: List[EngineTruck] = data["engine_trucks"]

    for vehicle_id, engine_truck in enumerate(engine_trucks):
        index = routing.Start(vehicle_id)
        if routing.IsEnd(index):
            continue

        optimized_trucks_used += 1

        stops: List[schemas.OptimizedStop] = []

        current_lat = engine_truck.start_lat
        current_lng = engine_truck.start_lng

        route_distance_km = 0.0
        route_minutes = 0.0
        route_demand_tons = 0.0
        prev_time_minutes = 0.0

        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)

            if node_index != data["depot_index"]:
                job = data["job_index_to_engine"][node_index]

                leg_km = haversine_km(current_lat, current_lng, job.lat, job.lng)
                leg_minutes = compute_leg_time_minutes(leg_km)

                eta_minutes = prev_time_minutes + leg_minutes

                stops.append(
                    schemas.OptimizedStop(
                        job_id=job.id,
                        customer_name=job.customer_name,
                        lat=job.lat,
                        lng=job.lng,
                        demand_tons=job.demand_tons,
                        service_minutes=job.service_minutes,
                        sequence_index=len(stops),
                        eta_minutes=eta_minutes,
                        leg_travel_minutes=leg_minutes,
                        leg_distance_km=leg_km,
                    )
                )

                route_distance_km += leg_km
                route_minutes += leg_minutes + job.service_minutes
                prev_time_minutes = eta_minutes + job.service_minutes
                current_lat, current_lng = job.lat, job.lng
                route_demand_tons += job.demand_tons

            index = solution.Value(routing.NextVar(index))

        # Return to depot
        leg_back_km = haversine_km(
            current_lat, current_lng, engine_truck.start_lat, engine_truck.start_lng
        )
        leg_back_minutes = compute_leg_time_minutes(leg_back_km)

        route_distance_km += leg_back_km
        route_minutes += leg_back_minutes
        prev_time_minutes += leg_back_minutes

        total_distance_km += route_distance_km
        total_driver_minutes += route_minutes
        max_route_minutes = max(max_route_minutes, int(round(route_minutes)))

        optimized_routes.append(
            schemas.OptimizedTruckRoute(
                truck_id=engine_truck.id,
                truck_name=engine_truck.name,
                capacity_tons=engine_truck.capacity_tons,
                stops=stops,
                total_route_distance_km=route_distance_km,
                total_route_time_minutes=float(round(route_minutes)),
                total_demand_tons=route_demand_tons,
            )
        )

    return (
        optimized_routes,
        total_distance_km,
        max_route_minutes,
        total_driver_minutes,
        optimized_trucks_used,
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def run_optimization(
    trucks: List[schemas.Truck],
    jobs: List[schemas.Job],
    max_route_minutes: float = float(MAX_ROUTE_MINUTES),
) -> schemas.OptimizeResult:
    """
    High-level optimization entrypoint.

    Behavior:
    ---------
    - Baseline is computed with the greedy heuristic (for comparison only).
    - OR-Tools computes an optimized plan that MINIMIZES the same cost model
      we use for ROI reporting:
        cost = (fuel + maintenance) * total_km + labor_rate * total_driver_minutes
    - We keep baseline_time_minutes / total_time_minutes as the max single-truck
      route (for UI display), but use total driver-minutes for costs.
    """
    # Quick sanity check before we call the heavy solver
    _quick_feasibility_check(trucks, jobs, max_route_minutes)

    # Baseline with greedy heuristic
    (
        baseline_distance_km,
        baseline_max_route_minutes,
        baseline_total_driver_minutes,
        baseline_trucks_used,
    ) = compute_baseline(trucks, jobs, max_route_minutes=max_route_minutes)

    # Optimized plan via OR-Tools (cost-minimizing)
    (
        routes,
        optimized_distance_km,
        optimized_max_route_minutes,
        optimized_total_driver_minutes,
        optimized_trucks_used,
    ) = _build_routes_with_ortools(trucks, jobs, max_route_minutes=max_route_minutes)

    # -------------------------
    # Cost / ROI modeling
    # -------------------------

    # Distance-based components
    baseline_fuel_cost = baseline_distance_km * FUEL_COST_PER_KM
    optimized_fuel_cost = optimized_distance_km * FUEL_COST_PER_KM

    baseline_maintenance_cost = baseline_distance_km * MAINTENANCE_COST_PER_KM
    optimized_maintenance_cost = optimized_distance_km * MAINTENANCE_COST_PER_KM

    # Labor: use TOTAL driver-minutes across all trucks
    baseline_labor_cost = (baseline_total_driver_minutes / 60.0) * DRIVER_COST_PER_HOUR
    optimized_labor_cost = (optimized_total_driver_minutes / 60.0) * DRIVER_COST_PER_HOUR

    # Overtime: not modeled in the "exact" cost function; set to 0 for now.
    baseline_overtime_cost = 0.0
    optimized_overtime_cost = 0.0

    # Totals
    baseline_total_cost = (
        baseline_fuel_cost
        + baseline_maintenance_cost
        + baseline_labor_cost
        + baseline_overtime_cost
    )
    optimized_total_cost = (
        optimized_fuel_cost
        + optimized_maintenance_cost
        + optimized_labor_cost
        + optimized_overtime_cost
    )

    daily_savings = baseline_total_cost - optimized_total_cost
    monthly_savings = daily_savings * WORKING_DAYS_PER_MONTH
    annual_savings = daily_savings * WORKING_DAYS_PER_YEAR

    # Optional: quick debug print so you can see the math in the terminal
    print(
        "[COST MODEL] fuel=$%.2f/km, maint=$%.2f/km, labor=$%.2f/hr"
        % (FUEL_COST_PER_KM, MAINTENANCE_COST_PER_KM, DRIVER_COST_PER_HOUR)
    )
    print(
        "[BASELINE] dist=%.1f km, max_route=%.1f min, total_driver=%.1f min -> fuel=$%.2f, maint=$%.2f, labor=$%.2f, total=$%.2f"
        % (
            baseline_distance_km,
            baseline_max_route_minutes,
            baseline_total_driver_minutes,
            baseline_fuel_cost,
            baseline_maintenance_cost,
            baseline_labor_cost,
            baseline_total_cost,
        )
    )
    print(
        "[OPTIMIZED] dist=%.1f km, max_route=%.1f min, total_driver=%.1f min -> fuel=$%.2f, maint=$%.2f, labor=$%.2f, total=$%.2f, daily_savings=$%.2f"
        % (
            optimized_distance_km,
            optimized_max_route_minutes,
            optimized_total_driver_minutes,
            optimized_fuel_cost,
            optimized_maintenance_cost,
            optimized_labor_cost,
            optimized_total_cost,
            daily_savings,
        )
    )

    return schemas.OptimizeResult(
        routes=routes,
        total_distance_km=optimized_distance_km,
        total_time_minutes=int(round(optimized_max_route_minutes)),
        baseline_distance_km=baseline_distance_km,
        baseline_time_minutes=float(int(round(baseline_max_route_minutes))),
        baseline_trucks_used=baseline_trucks_used,
        optimized_trucks_used=optimized_trucks_used,
        baseline_fuel_cost=baseline_fuel_cost,
        optimized_fuel_cost=optimized_fuel_cost,
        baseline_labor_cost=baseline_labor_cost,
        optimized_labor_cost=optimized_labor_cost,
        baseline_maintenance_cost=baseline_maintenance_cost,
        optimized_maintenance_cost=optimized_maintenance_cost,
        baseline_overtime_cost=baseline_overtime_cost,
        optimized_overtime_cost=optimized_overtime_cost,
        baseline_total_cost=baseline_total_cost,
        optimized_total_cost=optimized_total_cost,
        daily_savings=daily_savings,
        monthly_savings=monthly_savings,
        annual_savings=annual_savings,
    )
