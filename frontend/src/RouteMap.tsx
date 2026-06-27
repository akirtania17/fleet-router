// src/RouteMap.tsx

import React from "react";
import {
  MapContainer,
  TileLayer,
  Polyline,
  CircleMarker,
  Popup,
} from "react-leaflet";

import type { OptimizedTruckRoute } from "./types";

type RouteMapProps = {
  routes: OptimizedTruckRoute[];
};

// Color palette for different trucks
const COLORS = [
  "#ff3b30",
  "#34c759",
  "#007aff",
  "#ffcc00",
  "#af52de",
  "#ff9500",
  "#5ac8fa",
  "#5856d6",
];

export const RouteMap: React.FC<RouteMapProps> = ({ routes }) => {
  if (!routes || routes.length === 0) {
    return (
      <div
        style={{
          height: "320px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          color: "#94a3b8",
          fontSize: "0.9rem",
        }}
      >
        <p>(Map placeholder)</p>
        <p style={{ marginTop: "4px" }}>Run optimization to see truck routes.</p>
      </div>
    );
  }

  // Use the first stop of the first non‑empty route as the initial center
  const firstRouteWithStops = routes.find((r) => r.stops.length > 0);
  const firstStop = firstRouteWithStops?.stops[0];

  const center: [number, number] = firstStop
    ? [firstStop.lat, firstStop.lng]
    : [39.5, -98.35]; // fallback center of US

  return (
    <MapContainer
      center={center}
      zoom={11}
      style={{
        height: "384px", // ~h-96
        width: "100%",
        borderRadius: "24px",
        overflow: "hidden",
      }}
      scrollWheelZoom={true}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      />

      {routes.map((route, routeIndex) => {
        if (!route.stops || route.stops.length === 0) return null;

        const color = COLORS[routeIndex % COLORS.length];

        const latlngs: [number, number][] = route.stops.map((s) => [
          s.lat,
          s.lng,
        ]);

        return (
          <React.Fragment key={route.truck_id}>
            {/* Polyline for this truck's route */}
            <Polyline
              positions={latlngs}
              pathOptions={{ color, weight: 4, opacity: 0.9 }}
            />

            {/* Stops as circle markers */}
            {route.stops.map((stop) => (
              <CircleMarker
                key={stop.job_id}
                center={[stop.lat, stop.lng]}
                radius={5}
                pathOptions={{
                  color,
                  weight: 2,
                  fillColor: "#ffffff",
                  fillOpacity: 1,
                }}
              >
                <Popup>
                  <div style={{ fontSize: "0.8rem" }}>
                    <div style={{ fontWeight: 600 }}>{stop.customer_name}</div>
                    <div>Job ID: {stop.job_id}</div>
                    <div>Demand: {stop.demand_tons.toFixed(1)} t</div>
                    <div>Service: {stop.service_minutes} min</div>
                    <div>ETA: {stop.eta_minutes} min</div>
                  </div>
                </Popup>
              </CircleMarker>
            ))}
          </React.Fragment>
        );
      })}
    </MapContainer>
  );
};
