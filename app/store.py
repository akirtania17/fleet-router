# app/store.py
from typing import List
import random

from .schemas import Truck, TruckCreate, Job, JobCreate

_trucks: List[Truck] = []
_jobs: List[Job] = []
_next_truck_id = 1
_next_job_id = 1


def get_trucks() -> List[Truck]:
    return list(_trucks)


def get_jobs() -> List[Job]:
    return list(_jobs)


def add_truck(truck: TruckCreate) -> Truck:
    global _next_truck_id
    t = Truck(id=_next_truck_id, **truck.dict())
    _next_truck_id += 1
    _trucks.append(t)
    return t


def add_job(job: JobCreate) -> Job:
    global _next_job_id
    j = Job(id=_next_job_id, **job.dict())
    _next_job_id += 1
    _jobs.append(j)
    return j


def clear():
    global _trucks, _jobs, _next_truck_id, _next_job_id
    _trucks = []
    _jobs = []
    _next_truck_id = 1
    _next_job_id = 1


def reset_demo_data():
    clear()
    seed_demo_data()


def seed_demo_data():
    clear()

    # Depot around Chicago
    depot_lat = 41.8781
    depot_lng = -87.6298

    # --- RANDOM COUNT OF TRUCKS (1 to 8) ---
    num_trucks = random.randint(1, 8)

    for i in range(num_trucks):
        name = f"Truck {i+1}"
        capacity_tons = random.choice([8, 10, 12, 15, 20])
        start_lat = depot_lat + random.uniform(-0.02, 0.02)
        start_lng = depot_lng + random.uniform(-0.02, 0.02)

        add_truck(
            TruckCreate(
                name=name,
                capacity_tons=capacity_tons,
                start_lat=start_lat,
                start_lng=start_lng,
            )
        )

    customer_names = [
        "Alpha Steel", "Bravo Fabrication", "Chicago Auto Wreckers",
        "Delta Demolition", "Evergreen Metals", "Falcon Scrap",
        "Granite Recycling", "Harbor Industrial", "Ironclad Manufacturing",
        "Jackson Scrap", "Kilo Metal Works", "Lakeside Iron",
        "Midwest Shredders", "Northside Fabricators", "Omega Auto Salvage",
        "Prairie Steel", "Quantum Recycling", "River City Metals",
        "South Loop Scrap", "Union Yard"
    ]

    # --- RANDOM COUNT OF JOBS (1 to 20) ---
    num_jobs = random.randint(1, 20)

    for i in range(num_jobs):
        name = customer_names[i]
        lat = depot_lat + random.uniform(-0.15, 0.15)
        lng = depot_lng + random.uniform(-0.25, 0.25)
        demand_tons = random.uniform(1.0, 5.0)
        service_minutes = random.randint(10, 25)

        add_job(
            JobCreate(
                customer_name=name,
                lat=lat,
                lng=lng,
                demand_tons=demand_tons,
                service_minutes=service_minutes,
            )
        )
