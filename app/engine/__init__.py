# app/engine/__init__.py
"""
Public interface for the optimization engine layer.

FastAPI code should generally import from here rather than from the deeper
`core` module, so we can change internals without touching the API layer.
"""

from .core import (
    AVG_TRUCK_SPEED_KMH,
    MAX_ROUTE_MINUTES,
    compute_baseline,
    run_optimization,
)

__all__ = [
    "AVG_TRUCK_SPEED_KMH",
    "MAX_ROUTE_MINUTES",
    "compute_baseline",
    "run_optimization",
]
