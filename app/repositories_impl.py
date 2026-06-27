# app/repositories_impl.py

from __future__ import annotations

from typing import List

from . import schemas, store
from .repositories import YardRepository


class InMemoryYardRepository(YardRepository):
    """
    Thin adapter that turns the existing `store.py` module into a repository
    implementing the `YardRepository` protocol.
    """

    def get_trucks(self) -> List[schemas.Truck]:
        return store.get_trucks()

    def get_jobs(self) -> List[schemas.Job]:
        return store.get_jobs()

    def clear(self) -> None:
        # Your store already exposes `clear()`.
        # If you later rename it to `clear_all`, this still works.
        if hasattr(store, "clear"):
            store.clear()
        elif hasattr(store, "clear_all"):
            store.clear_all()


# Singleton repository instance used by services / optimizer
yard_repo = InMemoryYardRepository()
