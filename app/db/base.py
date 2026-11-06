"""Declarative base. P02-01: empty metadata (Alembic target)."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass