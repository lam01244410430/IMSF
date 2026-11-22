"""0008_recipe_columns - new nullable columns on community_recipes.

Adds the metadata columns the recipe import (Option B, Lam 2026-11-22)
needs before the 186 seed recipes can be imported with their
attribution intact: description, source_url, category, language,
difficulty, taste, slug and author (TEXT display name of the source
author -- NOT the users FK; ``author_id`` is untouched).

All columns are nullable with no defaults and no constraints, so
existing rows are unaffected. Follows the 0007 conventions
(docstring, ``revision`` / ``down_revision``).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_COLUMNS = (
    "description",
    "source_url",
    "category",
    "language",
    "difficulty",
    "taste",
    "slug",
    "author",
)


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column("community_recipes",
                      sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("community_recipes", name)
