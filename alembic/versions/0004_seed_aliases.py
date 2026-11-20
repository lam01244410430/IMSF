"""0004_seed_aliases — insert the 10 seed brand aliases (design §4).

Each alias maps a common brand name to a canonical ingredient seeded
by 0002; canonical ids are resolved by name at upgrade time.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# (alias, canonical_name)
SEEDS = [
    ("农夫山泉", "Nước suối"),
    ("怡宝", "Nước suối"),
    ("蒙牛", "Sữa tươi"),
    ("伊利", "Sữa tươi"),
    ("金龙鱼", "Dầu ăn"),
    ("海天", "Nước tương"),
    ("五常大米", "Gạo"),
    ("双汇", "Thịt ba chỉ"),
    ("正大", "Thịt gà"),
    ("光明", "Sữa tươi"),
]


def _table():
    return sa.table(
        "master_ingredient_aliases",
        sa.column("master_ingredient_id", PG_UUID()),
        sa.column("alias", sa.String(100)),
    )


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, canonical_name FROM master_ingredients")
    ).fetchall()
    by_name = {row.canonical_name: row.id for row in rows}
    missing = sorted({name for _, name in SEEDS} - set(by_name))
    if missing:
        raise RuntimeError(
            "0004 seed aliases: canonical ingredient(s) missing: %s"
            % ", ".join(missing)
        )
    op.bulk_insert(
        _table(),
        [
            {
                "master_ingredient_id": by_name[name],
                "alias": alias,
            }
            for alias, name in SEEDS
        ],
    )


def downgrade() -> None:
    table = _table()
    op.execute(
        table.delete().where(
            table.c.alias.in_([alias for alias, _ in SEEDS]))
    )
