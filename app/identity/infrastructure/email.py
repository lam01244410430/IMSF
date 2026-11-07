"""Email boundary. Production defaults to no provider; never print tokens."""
from app.identity.ports import EmailProvider as EmailProvider


class NoOpEmailProvider:
    """Explicit test double only; never automatically installed in production."""

    async def send(self, *, recipient: str, subject: str, body: str) -> None:
        pass
