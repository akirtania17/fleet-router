# app/repositories.py

from __future__ import annotations

from typing import Protocol, List

from . import schemas


class YardRepository(Protocol):
    """
    Abstract interface for all yard-related persistence.

    Today: implemented by our in-memory store.
    Tomorrow: Postgres, etc.
    """

    # Trucks
    def get_trucks(self) -> List[schemas.Truck]:
        ...

    # Jobs
    def get_jobs(self) -> List[schemas.Job]:
        ...

    # Clear/reset storage (used for demo seeding)
    def clear(self) -> None:
        ...
