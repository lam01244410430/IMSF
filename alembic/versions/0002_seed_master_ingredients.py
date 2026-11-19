"""0002_seed_master_ingredients — insert the 20 seed ingredients (design §4).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# (canonical_name, category, default_storage_zone, default_shelf_life_days)
SEEDS = [
    ("Thịt ba chỉ", "thịt", "fridge", 3),
    ("Thịt gà", "thịt", "fridge", 2),
    ("Thịt bò", "thịt", "fridge", 3),
    ("Cá", "cá", "fridge", 2),
    ("Tôm", "cá", "fridge", 2),
    ("Trứng gà", "trứng", "fridge", 21),
    ("Gạo", "đồ khô", "pantry", 180),
    ("Mì", "đồ khô", "pantry", 180),
    ("Sữa tươi", "sữa", "fridge", 5),
    ("Rau cải", "rau", "fridge", 4),
    ("Cà chua", "rau", "fridge", 5),
    ("Hành tây", "rau", "pantry", 30),
    ("Tỏi", "gia vị", "pantry", 60),
    ("Gừng", "gia vị", "fridge", 14),
    ("Dầu ăn", "gia vị", "pantry", 365),
    ("Muối", "gia vị", "pantry", 365),
    ("Đường", "gia vị", "pantry", 365),
    ("Nước tương", "gia vị", "pantry", 180),
    ("Đậu phụ", "đậu", "fridge", 3),
    ("Nước suối", "đồ uống", "pantry", 365),
]


def _table():
    return sa.table(
        "master_ingredients",
        sa.column("canonical_name", sa.String(100)),
        sa.column("category", sa.String(50)),
        sa.column("default_storage_zone", sa.String(20)),
        sa.column("default_shelf_life_days", sa.Integer()),
    )


def upgrade() -> None:
    op.bulk_insert(
        _table(),
        [
            {
                "canonical_name": name,
                "category": category,
                "default_storage_zone": zone,
                "default_shelf_life_days": days,
            }
            for name, category, zone, days in SEEDS
        ],
    )


def downgrade() -> None:
    table = _table()
    op.execute(
        table.delete().where(
            table.c.canonical_name.in_([name for name, _, _, _ in SEEDS]))
    )
