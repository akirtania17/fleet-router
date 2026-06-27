# app/sample_data.py

from __future__ import annotations

import random
from typing import Protocol

from . import schemas


class StoreLike(Protocol):
    """
    Minimal interface that any store/repository must implement
    in order to be used for demo seeding.

    Your in-memory store already matches this interface because it has:
        - add_truck(TruckCreate)
        - add_job(JobCreate)
    """

    def add_truck(self, t: schemas.TruckCreate) -> schemas.Truck: ...
    def add_job(self, j: schemas.JobCreate) -> schemas.Job: ...


# ---------------------------------------------------------------------------
# Customer names used for demo generation.
# You can expand this list as you want.
# ---------------------------------------------------------------------------

CUSTOMER_NAMES = [
    "River Scrap",
    "North Fabrication",
    "West Auto Dismantlers",
    "Downtown Machine",
    "Harbor Metals",
    "Eastside Recycling",
    "Industrial Steel Works",
    "Metro Demolition",
    "Prime Auto Recyclers",
    "Lakeview Fabrication",
    "Central Foundry",
    "Midtown Metal Works",
    "Green Valley Recycling",
    "Redline Steel Processing",
]


# ---------------------------------------------------------------------------
# Demo data loader with randomized truck & job counts
# ---------------------------------------------------------------------------

def load_sample_data(
    store: StoreLike,
    *,
    num_trucks: int | None = None,
    num_jobs: int | None = None,
) -> None:
    """
    Populate the given store with demo trucks & jobs.

    Behavior:
    ---------
    - If num_trucks / num_jobs are not provided, they are chosen randomly.
    - Adds trucks that all start at the "yard" (a fixed depot location).
    - Creates random jobs clustered geographically around that yard.

    This function does NOT clear the store — that is handled in:
        services.reset_demo_scenario()
    """

    # ----------------------------------------------------------
    # 1) Randomize fleet and workload size (if not provided)
    # ----------------------------------------------------------

    TRUCK_RANGE = (2, 5)    # You can tune these numbers
    JOB_RANGE = (10, 20)

    if num_trucks is None:
        num_trucks = random.randint(*TRUCK_RANGE)

    if num_jobs is None:
        num_jobs = random.randint(*JOB_RANGE)

    # ----------------------------------------------------------
    # 2) Define depot / yard location
    # ----------------------------------------------------------
    # You can change this to any city or keep it centered in US
    depot_lat = 39.099724    # Kansas City
    depot_lng = -94.578331

    # Helper for random nearby coordinates
    def random_near(lat: float, lng: float, max_offset: float = 0.15) -> tuple[float, float]:
        return (
            lat + random.uniform(-max_offset, max_offset),
            lng + random.uniform(-max_offset, max_offset),
        )

    # ----------------------------------------------------------
    # 3) Create trucks
    # ----------------------------------------------------------

    possible_capacities = [8, 10, 12, 15, 20]  # tons

    for i in range(num_trucks):
        t = schemas.TruckCreate(
            name=f"Truck {i + 1}",
            capacity_tons=random.choice(possible_capacities),
            start_lat=depot_lat,
            start_lng=depot_lng,
        )
        store.add_truck(t)

    # ----------------------------------------------------------
    # 4) Create jobs
    # ----------------------------------------------------------

    for _ in range(num_jobs):
        customer_name = random.choice(CUSTOMER_NAMES)
        lat, lng = random_near(depot_lat, depot_lng)

        demand_tons = round(random.uniform(0.5, 4.0), 1)
        service_minutes = random.randint(10, 45)

        j = schemas.JobCreate(
            customer_name=customer_name,
            lat=lat,
            lng=lng,
            demand_tons=demand_tons,
            service_minutes=service_minutes,
        )
        store.add_job(j)
