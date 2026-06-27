// src/types.ts

// ----- Core domain models coming from the FastAPI backend -----

export interface Truck {
  id: number;
  name: string;
  capacity_tons: number;
  start_lat: number;
  start_lng: number;
}

export interface Job {
  id: number;
  customer_name: string;
  lat: number;
  lng: number;
  demand_tons: number;
  service_minutes: number;
}

// ----- Optimized route models -----

export interface OptimizedStop {
  job_id: number;
  customer_name: string;
  lat: number;
  lng: number;
  demand_tons: number;
  service_minutes: number;

  sequence_index: number;
  eta_minutes: number;

  leg_travel_minutes: number;
  leg_distance_km: number;
}

export interface OptimizedTruckRoute {
  truck_id: number;
  truck_name: string;
  capacity_tons: number;

  total_route_distance_km: number;
  total_route_time_minutes: number;
  total_demand_tons: number;

  stops: OptimizedStop[];
}

export interface OptimizeResult {
  routes: OptimizedTruckRoute[];

  // Distance/time (aggregated)
  baseline_distance_km: number;
  total_distance_km: number;

  baseline_time_minutes: number; // longest driver's day, minutes
  total_time_minutes: number;    // longest driver's day, minutes

  baseline_trucks_used: number;
  optimized_trucks_used: number;

  // --- Cost model fields (simple cost model) ---
  baseline_fuel_cost: number;
  optimized_fuel_cost: number;

  baseline_labor_cost: number;
  optimized_labor_cost: number;

  baseline_maintenance_cost: number;
  optimized_maintenance_cost: number;

  baseline_overtime_cost: number;
  optimized_overtime_cost: number;

  baseline_total_cost: number;
  optimized_total_cost: number;

  daily_savings: number;
  monthly_savings: number;
  annual_savings: number;
}
