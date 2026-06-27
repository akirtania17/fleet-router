# app/schemas.py

from __future__ import annotations

from pydantic import BaseModel


# -----------------------
# Core domain models
# -----------------------


class TruckBase(BaseModel):
  name: str
  capacity_tons: float
  start_lat: float
  start_lng: float


class TruckCreate(TruckBase):
  pass


class Truck(TruckBase):
  id: int

  class Config:
    orm_mode = True


class JobBase(BaseModel):
  customer_name: str
  lat: float
  lng: float
  demand_tons: float
  service_minutes: float


class JobCreate(JobBase):
  pass


class Job(JobBase):
  id: int

  class Config:
    orm_mode = True


# -----------------------
# Optimization result models
# -----------------------


class OptimizedStop(BaseModel):
  job_id: int
  customer_name: str
  lat: float
  lng: float

  demand_tons: float
  service_minutes: float

  # Order within the truck's route (0-based index)
  sequence_index: int

  # Travel + arrival timing for this leg
  eta_minutes: float  # minutes from route start to arrival at this stop
  leg_travel_minutes: float  # minutes travelled from previous stop (or depot)

  leg_distance_km: float  # distance from previous stop (or depot)


class OptimizedTruckRoute(BaseModel):
  truck_id: int
  truck_name: str
  capacity_tons: float

  # Ordered stops assigned to this truck
  stops: list[OptimizedStop]

  # Totals for this truck's route
  total_route_distance_km: float
  total_route_time_minutes: float  # includes travel + service time

  # Total tons this truck is carrying across its route
  total_demand_tons: float


class OptimizeResult(BaseModel):
  # Optimized routes per truck
  routes: list[OptimizedTruckRoute]

  # Aggregated optimized totals
  total_distance_km: float
  total_time_minutes: int

  # Baseline (naive) metrics for comparison
  baseline_distance_km: float
  baseline_time_minutes: float
  baseline_trucks_used: int

  # How many trucks actually got used in the optimized solution
  optimized_trucks_used: int

  # -------------------------
  # Cost / ROI metrics
  # -------------------------

  # Fuel cost estimate (USD) for baseline vs optimized plan
  baseline_fuel_cost: float
  optimized_fuel_cost: float

  # Driver labor cost estimate (USD) for baseline vs optimized plan
  baseline_labor_cost: float
  optimized_labor_cost: float

  # Maintenance / wear cost estimate (USD) for baseline vs optimized
  baseline_maintenance_cost: float
  optimized_maintenance_cost: float

  # Overtime premium (USD) if overtime costing is enabled
  baseline_overtime_cost: float
  optimized_overtime_cost: float

  # Total daily operating cost (fuel + labor + maintenance + overtime)
  baseline_total_cost: float
  optimized_total_cost: float

  # Estimated savings (USD)
  # "Daily" assumes one run of this scenario per operating day.
  daily_savings: float
  monthly_savings: float
  annual_savings: float
