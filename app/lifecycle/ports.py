"""Step 2 read-only ports. No enqueue, claim or stock mutation capability."""
from datetime import date
from typing import Protocol


class LifecycleRepository(Protocol):
    async def lot_page(self, hid: int, limit: int, position: int | None,
                       filters: dict, local_date: date) -> list[dict]: ...
    async def alert_page(self, hid: int, limit: int, position: int | None,
                         filters: dict) -> list[dict]: ...
    async def alert(self, hid: int, identifier: int) -> dict | None: ...
