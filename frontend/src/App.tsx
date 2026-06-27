// src/App.tsx
import { useEffect, useState } from "react";
import "./App.css";

import { RouteMap } from "./RouteMap";

import type {
  Truck,
  Job,
  OptimizeResult as BaseOptimizeResult,
  OptimizedTruckRoute,
} from "./types";

const API_BASE = "http://127.0.0.1:8000";

type OptimizeResult = BaseOptimizeResult & {
  routes: OptimizedTruckRoute[];
  baseline_time_minutes?: number;
  baseline_trucks_used?: number;
  total_time_minutes?: number;
  optimized_trucks_used?: number;
};

// ---------- formatting helpers ----------

function fmtFixed(value: unknown, digits: number): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function fmtMinutes(value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return `${Math.round(value)} min`;
}

function fmtLatLng(lat: unknown, lng: unknown): string {
  if (typeof lat !== "number" || typeof lng !== "number") return "—";
  return `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
}

function fmtCurrency(value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

// ---------- generic API helper (for trucks / jobs / reset) ----------

async function getJson<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${res.statusText}`);
  }
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

// ---------- main component ----------

function App() {
  const [trucks, setTrucks] = useState<Truck[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [optResult, setOptResult] = useState<OptimizeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ----- load trucks + jobs -----

  async function loadInitial() {
    try {
      setError(null);
      const [t, j] = await Promise.all([
        getJson<Truck[]>("/trucks"),
        getJson<Job[]>("/jobs"),
      ]);

      setTrucks(Array.isArray(t) ? t : []);
      setJobs(Array.isArray(j) ? j : []);
    } catch (e) {
      console.error(e);
      setError("Failed to load trucks / jobs from API.");
    }
  }

  useEffect(() => {
    loadInitial();
  }, []);

  // ----- reset demo -----

  async function resetDemo() {
    setLoading(true);
    try {
      setError(null);
      await getJson<void>("/demo/reset", { method: "POST" });
      await loadInitial();
      setOptResult(null);
    } catch (e) {
      console.error(e);
      setError("Failed to reset demo data.");
    } finally {
      setLoading(false);
    }
  }

  // ----- run optimization (special-cased) -----

  async function runOptimization() {
    setLoading(true);
    try {
      setError(null);

      const res = await fetch(`${API_BASE}/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      const text = await res.text();

      if (!res.ok) {
        // Try to build a *useful* message based on backend JSON
        let message = "Failed to run optimization.";

        try {
          const parsed = text ? JSON.parse(text) : null;

          // Expected shape from our custom handler:
          // { detail: { type: "infeasible_optimization", message, diagnostics } }
          if (
            parsed &&
            typeof parsed === "object" &&
            "detail" in parsed &&
            typeof parsed.detail === "object"
          ) {
            const detail: any = parsed.detail;

            if (detail.type === "infeasible_optimization") {
              const d = detail.diagnostics ?? {};
              const parts: string[] = [];

              if (
                typeof d.total_demand_tons === "number" &&
                typeof d.total_capacity_tons === "number"
              ) {
                parts.push(
                  `Total demand is ${d.total_demand_tons.toFixed(
                    1
                  )}t but fleet capacity is only ${d.total_capacity_tons.toFixed(
                    1
                  )}t.`
                );
              }

              if (
                typeof d.total_service_minutes === "number" &&
                typeof d.total_time_budget_minutes === "number"
              ) {
                parts.push(
                  `Total service time requested is ${Math.round(
                    d.total_service_minutes
                  )} minutes, but driver time budget is ${Math.round(
                    d.total_time_budget_minutes
                  )} minutes (ignoring travel).`
                );
              }

              const base =
                typeof detail.message === "string"
                  ? detail.message
                  : "The current mix of trucks and jobs cannot be fully served within today's capacity/time constraints.";

              message = `Cannot optimize routes for this scenario. ${base}${
                parts.length ? " " + parts.join(" ") : ""
              }`;
            } else if (typeof detail.message === "string") {
              // Some other structured backend error
              message = detail.message;
            }
          } else if (
            parsed &&
            typeof parsed === "object" &&
            "detail" in parsed &&
            typeof parsed.detail === "string"
          ) {
            // Default FastAPI error: { detail: "..." }
            const detailStr = parsed.detail as string;
            message = detailStr;
          }
        } catch (parseErr) {
          console.error("Failed to parse error JSON:", parseErr, text);
        }

        throw new Error(message);
      }

      const data: OptimizeResult = text
        ? (JSON.parse(text) as OptimizeResult)
        : (undefined as any);
      setOptResult(data);
    } catch (e: unknown) {
      console.error(e);
      if (e instanceof Error && e.message) {
        setError(e.message);
      } else {
        setError("Failed to run optimization.");
      }
    } finally {
      setLoading(false);
    }
  }

  // ----- summary values -----

  const baselineKm = optResult?.baseline_distance_km;
  const optimizedKm = optResult?.total_distance_km;

  const baselineLabel =
    baselineKm != null ? `${fmtFixed(baselineKm, 1)} km` : "—";
  const optimizedLabel =
    optimizedKm != null ? `${fmtFixed(optimizedKm, 1)} km` : "—";

  const baselineTime = fmtMinutes(optResult?.baseline_time_minutes);
  const optimizedTime = fmtMinutes(optResult?.total_time_minutes);

  const baselineTrucks =
    typeof optResult?.baseline_trucks_used === "number"
      ? optResult?.baseline_trucks_used
      : null;
  const optimizedTrucks =
    typeof optResult?.optimized_trucks_used === "number"
      ? optResult?.optimized_trucks_used
      : null;

  const dailySavingsLabel = fmtCurrency(optResult?.daily_savings);
  // Optional if you want to surface it later:
  // const monthlySavingsLabel = fmtCurrency(optResult?.monthly_savings);

  // ---------- render ----------

  return (
    <div className="app-root">
      <div className="app-shell">
        {/* Top bar */}
        <header className="app-header">
          <div className="logo-block">
            <div className="logo-badge">SF</div>
            <div className="logo-text">
              <div className="logo-title">ScrapFlo</div>
              <div className="logo-subtitle">
                Route optimization for scrap &amp; recycling fleets
              </div>
            </div>
          </div>
          <div className="founders">
            <span>Founded by</span>
            <span className="founders-names">
              &nbsp;Aumit Kirtania &amp; Farzad Ferdous
            </span>
          </div>
        </header>

        {/* Hero */}
        <section className="hero">
          <div className="hero-text">
            <p className="eyebrow">Route Optimization Software</p>
            <h1 className="hero-title">
              <span className="hero-gradient">
                Optimization software for the
              </span>
              <br />
              <span className="hero-gradient">$70B scrap &amp; recycling</span>{" "}
              industry.
            </h1>
            <p className="hero-subtitle">
              ScrapFlo turns messy pickup schedules into efficient,
              capacity-aware truck routes — in seconds, not spreadsheets.
            </p>

            <div className="hero-actions">
              <button
                onClick={runOptimization}
                disabled={loading || !jobs.length}
                className="btn btn-primary"
              >
                {loading ? "Optimizing…" : "Run Optimization"}
              </button>
              <button
                onClick={resetDemo}
                disabled={loading}
                className="btn btn-ghost"
              >
                Reset Demo Data
              </button>
              <div className="status-pill">
                <span className="status-dot" />
                <span className="status-text">
                  {optResult ? "Routes optimized" : "Ready for first run"}
                </span>
              </div>
            </div>

            {error && <div className="error-banner">{error}</div>}
          </div>

          {/* Snapshot card in hero */}
          <div className="snapshot-card">
            <div className="snapshot-header">Optimization snapshot</div>
            <div className="snapshot-grid">
              <div className="snapshot-item">
                <div className="snapshot-label">Baseline distance</div>
                <div className="snapshot-value">{baselineLabel}</div>
                <div className="snapshot-sub">
                  Time: <span>{baselineTime}</span>
                </div>
                <div className="snapshot-sub">
                  Trucks:{" "}
                  <span>
                    {baselineTrucks != null ? baselineTrucks : "—"}
                  </span>
                </div>
              </div>
              <div className="snapshot-item snapshot-item-highlight">
                <div className="snapshot-label">Optimized distance</div>
                <div className="snapshot-value">{optimizedLabel}</div>
                <div className="snapshot-sub">
                  Time: <span>{optimizedTime}</span>
                </div>
                <div className="snapshot-sub">
                  Trucks:{" "}
                  <span>
                    {optimizedTrucks != null ? optimizedTrucks : "—"}
                  </span>
                </div>
                <div className="snapshot-sub">
                  Est. daily savings: <span>{dailySavingsLabel}</span>
                </div>
              </div>
              <div className="snapshot-item">
                <div className="snapshot-label">Active trucks</div>
                <div className="snapshot-value">{trucks.length}</div>
                <div className="snapshot-sub">
                  All starting at a shared Kansas depot
                </div>
              </div>
              <div className="snapshot-item">
                <div className="snapshot-label">Open jobs</div>
                <div className="snapshot-value">{jobs.length}</div>
                <div className="snapshot-sub">
                  Each with weight &amp; service time constraints
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Map section */}
        <section className="section">
          <div className="section-header">
            <h2>Route map</h2>
            {optResult && (
              <span className="section-caption">
                Showing {optResult.routes.length} optimized truck routes
              </span>
            )}
          </div>
          <div className="card card-map">
            {optResult && optResult.routes && optResult.routes.length > 0 ? (
              <RouteMap routes={optResult.routes} />
            ) : (
              <div className="map-placeholder">
                <p className="map-placeholder-title">(Map placeholder)</p>
                <p>Run optimization to see truck routes drawn over Kansas.</p>
                <p className="map-placeholder-sub">
                  Current optimized routes:{" "}
                  {optResult ? optResult.routes.length : 0}
                </p>
              </div>
            )}
          </div>
        </section>

        {/* Tables */}
        <section className="section section-grid">
          {/* Trucks */}
          <div className="card">
            <div className="section-header">
              <h2>Trucks</h2>
              <span className="section-caption">
                {trucks.length} active trucks
              </span>
            </div>
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Truck</th>
                    <th>Capacity (t)</th>
                    <th>Start (lat, lng)</th>
                  </tr>
                </thead>
                <tbody>
                  {trucks.map((t, i) => {
                    const rawCap =
                      (t as any).capacity_tons ?? (t as any).capacity_weight;
                    return (
                      <tr key={t.id ?? i}>
                        <td>{t.name ?? "Truck"}</td>
                        <td>{fmtFixed(rawCap, 1)}</td>
                        <td>
                          {fmtLatLng(
                            (t as any).start_lat,
                            (t as any).start_lng
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Jobs */}
          <div className="card">
            <div className="section-header">
              <h2>Jobs</h2>
              <span className="section-caption">{jobs.length} pickups</span>
            </div>
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th>Demand (t)</th>
                    <th>Service (min)</th>
                    <th>Location</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j, i) => {
                    const rawDemand =
                      (j as any).demand_tons ?? (j as any).demand_weight;
                    const rawService =
                      (j as any).service_minutes ??
                      (j as any).expected_service_minutes;
                    return (
                      <tr key={j.id ?? i}>
                        <td>{j.customer_name ?? "Job"}</td>
                        <td>{fmtFixed(rawDemand, 1)}</td>
                        <td>{fmtMinutes(rawService)}</td>
                        <td>{fmtLatLng((j as any).lat, (j as any).lng)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <footer className="app-footer">
          <span>ScrapFlo · internal MVP</span>
          <span className="footer-muted">
            Synthetic demo data clustered around a Kansas depot.
          </span>
        </footer>
      </div>
    </div>
  );
}

export default App;
