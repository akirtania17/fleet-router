# app/services.py

from __future__ import annotations

from typing import List

from . import schemas, sample_data, store
from .repositories_impl import yard_repo
from . import optimizer


def list_trucks() -> List[schemas.Truck]:
    """
    Read-only view of all trucks for the current yard/store.
    """
    return yard_repo.get_trucks()


def list_jobs() -> List[schemas.Job]:
    """
    Read-only view of all jobs (stops) for the current yard/store.
    """
    return yard_repo.get_jobs()


def reset_demo_scenario() -> None:
    """
    Clear the current in-memory store and repopulate it with demo data.

    This is the single place that knows:
    - how to clear the store
    - how to seed it with sample data
    """
    yard_repo.clear()
    # sample_data knows how to seed trucks + jobs given the store module
    sample_data.load_sample_data(store)


def optimize_current_state() -> schemas.OptimizeResult:
    """
    Run the optimization engine using the current trucks + jobs in the repo.

    This hides where data comes from (in-memory vs DB), so later you can:
    - swap the store implementation
    - add auth / multi-tenancy
    without touching the API layer.
    """
    return optimizer.optimize()
