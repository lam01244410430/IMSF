"""Identity integration boundaries; implementations never own transactions."""

from typing import Protocol


class EmailProvider(Protocol):
    # MANAGER PROPOSAL (merge gate): invitations persist without a provider,
    # remain not emailed, and never return their token to the caller.
    async def send(self, *, recipient: str, subject: str, body: str) -> None: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, encoded: str) -> bool: ...


class IdentityRepository(Protocol):
    """Reads return persistence records to the future application layer."""

    async def user_by_email(self, email: str, *, lock: bool = False) -> object | None: ...
    async def active_member(self, household_id: int, user_id: int, *, lock: bool = False) -> object | None: ...
    async def lock_household(self, household_id: int) -> object | None: ...
