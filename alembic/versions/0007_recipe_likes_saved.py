"""0007_recipe_likes_saved - recipe like/save tables (Phase 3 blog).

Creates ``recipe_likes`` and ``saved_recipes`` (identical shape): one
row per (recipe, user), UNIQUE(recipe_id, user_id), both FKs
ON DELETE CASCADE. Follows the 0003 conventions (``_pk()`` /
``_timestamps()`` helpers, ``PG_UUID``).

``community_recipes.likes_count`` is maintained by the application
(like/unlike endpoints in app/api/recipes.py) and is NOT a generated
column -- the counter is incremented only when a new like row is
actually inserted (ON CONFLICT DO NOTHING) and decremented only when
a row is actually deleted, never below 0 (the table already has
CHECK (likes_count >= 0)).

``recipe_comments`` already exists (Phase 2) and is NOT touched here.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _pk():
    return sa.Column("id", PG_UUID(), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def _timestamps():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      nullable=False, server_default=sa.text("now()"))]


def _create_like_table(table: str, uq_name: str) -> None:
    op.create_table(
        table,
        _pk(),
        sa.Column("recipe_id", PG_UUID(), sa.ForeignKey(
            "community_recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", PG_UUID(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("recipe_id", "user_id", name=uq_name),
    )


def upgrade() -> None:
    _create_like_table("recipe_likes", "uq_recipe_likes_recipe_user")
    _create_like_table("saved_recipes", "uq_saved_recipes_recipe_user")


def downgrade() -> None:
    op.drop_table("saved_recipes")
    op.drop_table("recipe_likes")
