# app/main.py

from __future__ import annotations

from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import schemas, services
from .engine.core import InfeasibleOptimizationError

# ------------------------------------------------------------------
# FastAPI app + CORS (wide open for local dev)
# ------------------------------------------------------------------

app = FastAPI(title="ScrapFlo MVP API")

# Wide-open CORS so localhost:5173 -> 127.0.0.1:8000 works
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Exception handler for infeasible optimization problems
# ------------------------------------------------------------------


@app.exception_handler(InfeasibleOptimizationError)
async def infeasible_optimization_handler(
    request: Request,
    exc: InfeasibleOptimizationError,
) -> JSONResponse:
    """
    Convert engine-level infeasibility into a clean HTTP 400 response
    with structured diagnostics that the frontend (or CLI) can inspect.
    """
    payload = {
        "detail": {
            "type": "infeasible_optimization",
            "message": str(exc),
            "diagnostics": exc.diagnostics,
        }
    }
    return JSONResponse(
        status_code=400,
        content=payload,
        headers={"Access-Control-Allow-Origin": "*"},
    )


# ------------------------------------------------------------------
# Startup: seed in-memory store with demo data
# ------------------------------------------------------------------


@app.on_event("startup")
def startup() -> None:
    """
    Seed the in-memory store with demo trucks + jobs on server start.

    We route this through the services layer so that later, when you:
    - add a real DB,
    - add multi-tenant yards,
    - or remove demo mode in production,
    you only need to touch `services.reset_demo_scenario`, not every route.
    """
    services.reset_demo_scenario()


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------


@app.get("/ping")
def ping() -> dict:
    """
    Simple health check endpoint.
    """
    return {"status": "ok"}


# ------------------------------------------------------------------
# Read-only truck / job lists for the frontend
# ------------------------------------------------------------------


@app.get("/trucks", response_model=list[schemas.Truck])
def list_trucks() -> list[schemas.Truck]:
    """
    Return the current list of trucks in the yard.
    """
    return services.list_trucks()


@app.get("/jobs", response_model=list[schemas.Job])
def list_jobs() -> list[schemas.Job]:
    """
    Return the current list of jobs (stops) in the yard.
    """
    return services.list_jobs()


# ------------------------------------------------------------------
# Demo reset endpoint (used by the MVP frontend)
# ------------------------------------------------------------------


@app.post("/demo/reset")
def reset_demo() -> dict:
    """
    Reset the in-memory store and repopulate with random demo data.

    Frontend calls: POST http://127.0.0.1:8000/demo/reset
    """
    services.reset_demo_scenario()
    return {"status": "ok"}


# ------------------------------------------------------------------
# CORS preflight for /optimize
# ------------------------------------------------------------------


@app.options("/optimize")
def options_optimize() -> Response:
    """
    Manual CORS preflight handler so the browser is happy when the
    React app POSTs to /optimize.
    """
    resp = Response()
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


# ------------------------------------------------------------------
# Main optimization endpoint
# ------------------------------------------------------------------


@app.post("/optimize", response_model=schemas.OptimizeResult)
def run_optimization(response: Response) -> schemas.OptimizeResult:
    """
    Frontend calls: POST http://127.0.0.1:8000/optimize

    We keep this function super thin: it delegates to the services layer,
    which then calls into the optimization engine.
    """
    result = services.optimize_current_state()

    # Make 100% sure the CORS header is on this response too
    response.headers["Access-Control-Allow-Origin"] = "*"

    return result
