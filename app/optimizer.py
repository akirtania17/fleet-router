# app/optimizer.py
"""
Thin adapter between the FastAPI layer and the optimization engine.

Previously this module contained all of the VRP / routing logic and also
reached directly into the in-memory `store`. That made it hard to unit-test
and to eventually swap out the storage backend.

Now:
  * All heavy-duty optimization logic lives in `app.engine.core`.
  * This file is just a small helper that:
        - pulls data from the yard repository
        - calls `engine.run_optimization`
        - returns a `schemas.OptimizeResult`.
"""

from __future__ import annotations

from . import schemas
from .engine import run_optimization
from .repositories_impl import yard_repo


def optimize() -> schemas.OptimizeResult:
    """
    Main optimization entrypoint used by the FastAPI route.

    The FastAPI layer (via services) calls this with no arguments; under
    the hood we grab the current set of trucks and jobs from the yard
    repository and hand them off to the engine layer.
    """
    # Get the current problem instance from the repository
    trucks = yard_repo.get_trucks()
    jobs = yard_repo.get_jobs()

    # Delegate to the stateless engine
    return run_optimization(trucks, jobs)
