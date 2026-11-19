"""0001_initial — create the 13 Phase 1 tables (design §3).

Order follows FK dependency:
users → households → household_members → master_ingredients → receipts →
receipt_lines → inventory_items → equipments → community_recipes →
recipe_ingredients → recipe_ratings → recipe_comments → cooksnaps.

Revision ID: 0001
Revises: (none)
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _pk():
    return sa.Column("id", PG_UUID(), primary_key=True,
                     server_default=sa.text("gen_random_uuid()"))


def _timestamps(with_updated=True):
    cols = [sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      nullable=False, server_default=sa.text("now()"))]
    if with_updated:
        cols.append(sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                              nullable=False, server_default=sa.text("now()")))
    return cols


def upgrade() -> None:
    # 3.1 users
    op.create_table(
        "users",
        _pk(),
        sa.Column("phone", sa.String(20), nullable=True, unique=True),
        sa.Column("wechat_openid", sa.String(64), nullable=True, unique=True),
        sa.Column("wechat_unionid", sa.String(64), nullable=True, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("phone IS NOT NULL OR wechat_openid IS NOT NULL",
                           name="ck_users_login_channel"),
    )

    # 3.2 households
    op.create_table(
        "households",
        _pk(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("default_currency", sa.CHAR(3), nullable=False,
                  server_default=sa.text("'CNY'")),
        sa.Column("timezone", sa.String(50), nullable=False,
                  server_default=sa.text("'Asia/Shanghai'")),
        sa.Column("locale", sa.String(10), nullable=False,
                  server_default=sa.text("'zh-CN'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("default_currency IN ('CNY', 'VND')",
                           name="ck_households_currency"),
    )

    # 3.3 household_members
    op.create_table(
        "household_members",
        _pk(),
        sa.Column("user_id", PG_UUID(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("household_id", PG_UUID(), sa.ForeignKey(
            "households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False,
                  server_default=sa.text("'member'")),
        sa.Column("joined_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('owner', 'member')",
                           name="ck_household_members_role"),
        sa.UniqueConstraint("user_id", "household_id",
                            name="uq_household_members_user_household"),
    )
    # Exactly 1 owner per household (partial unique index, design §3.3).
    op.create_index(
        "uq_household_owner", "household_members", ["household_id"],
        unique=True, postgresql_where=sa.text("role = 'owner'"))

    # 3.10 master_ingredients (before receipts: receipt_lines references it)
    op.create_table(
        "master_ingredients",
        _pk(),
        sa.Column("canonical_name", sa.String(100), nullable=False,
                  unique=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("default_storage_zone", sa.String(20), nullable=True),
        sa.Column("default_shelf_life_days", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "default_storage_zone IN ('frozen', 'fridge', 'pantry')",
            name="ck_master_ingredients_zone"),
        sa.CheckConstraint("default_shelf_life_days >= 0",
                           name="ck_master_ingredients_shelf_life"),
    )

    # 3.4 receipts
    op.create_table(
        "receipts",
        _pk(),
        sa.Column("household_id", PG_UUID(), sa.ForeignKey(
            "households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_user_id", PG_UUID(), sa.ForeignKey(
            "users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("store_name", sa.String(200), nullable=True),
        sa.Column("purchased_at", sa.TIMESTAMP(timezone=True),
                  nullable=True),
        sa.Column("total_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column("ocr_raw_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True),
                  nullable=True),
        *_timestamps(),
        sa.CheckConstraint("total_amount >= 0",
                           name="ck_receipts_total_amount"),
        sa.CheckConstraint("currency IN ('CNY', 'VND')",
                           name="ck_receipts_currency"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed',"
            " 'needs_review')",
            name="ck_receipts_status"),
    )
    op.create_index("ix_receipts_household_created", "receipts",
                    ["household_id", "created_at"])

    # 3.5 receipt_lines
    op.create_table(
        "receipt_lines",
        _pk(),
        sa.Column("receipt_id", PG_UUID(), sa.ForeignKey(
            "receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("canonical_ingredient_id", PG_UUID(), sa.ForeignKey(
            "master_ingredients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_stock_item", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("currency IN ('CNY', 'VND')",
                           name="ck_receipt_lines_currency"),
        sa.UniqueConstraint("receipt_id", "line_no",
                            name="uq_receipt_lines_receipt_line_no"),
    )
    op.create_index("ix_receipt_lines_receipt_id", "receipt_lines",
                    ["receipt_id"])

    # 3.6 inventory_items
    op.create_table(
        "inventory_items",
        _pk(),
        sa.Column("household_id", PG_UUID(), sa.ForeignKey(
            "households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receipt_id", PG_UUID(), sa.ForeignKey(
            "receipts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("receipt_line_id", PG_UUID(), sa.ForeignKey(
            "receipt_lines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("canonical_ingredient_id", PG_UUID(), sa.ForeignKey(
            "master_ingredients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("storage_zone", sa.String(20), nullable=True),
        sa.Column("added_date", sa.Date(), nullable=False,
                  server_default=sa.text("CURRENT_DATE")),
        sa.Column("auto_expiry_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=sa.text("'fresh'")),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True),
                  nullable=True),
        *_timestamps(),
        sa.CheckConstraint("quantity > 0",
                           name="ck_inventory_items_quantity"),
        sa.CheckConstraint("currency IN ('CNY', 'VND')",
                           name="ck_inventory_items_currency"),
        sa.CheckConstraint(
            "storage_zone IN ('frozen', 'fridge', 'pantry')",
            name="ck_inventory_items_zone"),
        sa.CheckConstraint(
            "status IN ('fresh', 'expiring', 'expired', 'consumed')",
            name="ck_inventory_items_status"),
    )
    op.create_index("ix_inventory_household_status_expiry",
                    "inventory_items",
                    ["household_id", "status", "auto_expiry_date"])

    # 3.7 equipments
    op.create_table(
        "equipments",
        _pk(),
        sa.Column("household_id", PG_UUID(), sa.ForeignKey(
            "households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_type", sa.String(50), nullable=False),
        sa.Column("brand_model", sa.String(200), nullable=True),
        sa.Column("usage_intensity", sa.String(20), nullable=True),
        sa.Column("last_maintained_at", sa.TIMESTAMP(timezone=True),
                  nullable=True),
        sa.Column("next_maintenance_date", sa.Date(), nullable=True),
        sa.Column("rag_maintenance_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=sa.text("'active'")),
        sa.Column("household_size", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "usage_intensity IN ('low', 'medium', 'high')",
            name="ck_equipments_usage_intensity"),
        sa.CheckConstraint("household_size > 0",
                           name="ck_equipments_household_size"),
        sa.CheckConstraint("status IN ('active', 'retired')",
                           name="ck_equipments_status"),
    )

    # 3.8 community_recipes
    op.create_table(
        "community_recipes",
        _pk(),
        sa.Column("author_id", PG_UUID(), sa.ForeignKey(
            "users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("cover_image", sa.Text(), nullable=True),
        sa.Column("steps_json", JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("cook_time", sa.Integer(), nullable=True),
        sa.Column("likes_count", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=sa.text("'published'")),
        *_timestamps(),
        sa.CheckConstraint("likes_count >= 0",
                           name="ck_community_recipes_likes_count"),
        sa.CheckConstraint("status IN ('draft', 'published', 'hidden')",
                           name="ck_community_recipes_status"),
    )
    op.create_index("ix_recipes_status_created", "community_recipes",
                    ["status", "created_at"])

    # 3.9 recipe_ingredients
    op.create_table(
        "recipe_ingredients",
        _pk(),
        sa.Column("recipe_id", PG_UUID(), sa.ForeignKey(
            "community_recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_ingredient_id", PG_UUID(), sa.ForeignKey(
            "master_ingredients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_name", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("is_main_ingredient", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_recipe_ingredients_recipe_id",
                    "recipe_ingredients", ["recipe_id"])

    # 3.11 recipe_ratings
    op.create_table(
        "recipe_ratings",
        _pk(),
        sa.Column("recipe_id", PG_UUID(), sa.ForeignKey(
            "community_recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", PG_UUID(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("stars BETWEEN 1 AND 5",
                           name="ck_recipe_ratings_stars"),
        sa.UniqueConstraint("recipe_id", "user_id",
                            name="uq_recipe_ratings_recipe_user"),
    )

    # 3.12 recipe_comments
    op.create_table(
        "recipe_comments",
        _pk(),
        sa.Column("recipe_id", PG_UUID(), sa.ForeignKey(
            "community_recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", PG_UUID(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("parent_comment_id", PG_UUID(), sa.ForeignKey(
            "recipe_comments.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
    )

    # 3.13 cooksnaps
    op.create_table(
        "cooksnaps",
        _pk(),
        sa.Column("recipe_id", PG_UUID(), sa.ForeignKey(
            "community_recipes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", PG_UUID(), sa.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    for table in ("cooksnaps", "recipe_comments", "recipe_ratings",
                  "recipe_ingredients", "community_recipes", "equipments",
                  "inventory_items", "receipt_lines", "receipts",
                  "master_ingredients", "household_members",
                  "households", "users"):
        op.drop_table(table)
