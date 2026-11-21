"""Constraint tests for the Phase 1 migrations (design §3/§4).

Runs against a disposable ``imsf_test`` database on the same Postgres
server as DATABASE_URL, so the dev ``imsf`` data is never touched.
The fixture creates the test DB if missing and runs ``alembic upgrade
head`` against it, so the tests verify the real migrations, not a copy.

DATABASE_URL defaults to the CI service URL (postgres:16, user imsf)
when unset, matching .github/workflows/ci.yml.
"""

import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://imsf:imsf@127.0.0.1:5432/imsf"
)
TEST_DB = "imsf_test"


def _base_url():
    return os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def _test_url():
    url = urlparse(_base_url())
    return urlunparse(url._replace(path=f"/{TEST_DB}"))


def _admin_url():
    # Maintenance DB that always exists: the admin connection only issues
    # CREATE DATABASE, so it must not point at the (not yet created) test DB.
    url = urlparse(_base_url())
    return urlunparse(url._replace(path="/postgres"))


@pytest.fixture(scope="module")
def test_engine():
    from alembic import command
    from alembic.config import Config

    admin = sa.create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB},
        ).first()
        if not exists:
            conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _test_url())
    # NOTE: alembic/env.py overrides sqlalchemy.url from DATABASE_URL at
    # migration runtime, so point the env var at the test DB for the
    # upgrade (restored afterwards). Without this the upgrade silently
    # runs against the dev DB (already at head -> no-op) and the test
    # DB stays empty.
    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _test_url()
    try:
        command.upgrade(cfg, "head")
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url

    engine = sa.create_engine(_test_url())
    yield engine
    engine.dispose()


@pytest.fixture
def conn(test_engine):
    connection = test_engine.connect()
    trans = connection.begin()
    yield connection
    trans.rollback()
    connection.close()


# -- fixtures -------------------------------------------------------------

def mk_user(conn, phone="13800000001"):
    return conn.execute(
        text("INSERT INTO users (phone, name) VALUES (:phone, 'Test User')"
             " RETURNING id"),
        {"phone": phone},
    ).scalar_one()


def mk_household(conn):
    return conn.execute(
        text("INSERT INTO households (name) VALUES ('Test Home')"
             " RETURNING id"),
    ).scalar_one()


def add_member(conn, user_id, household_id, role="member"):
    return conn.execute(
        text("INSERT INTO household_members (user_id, household_id, role)"
             " VALUES (:u, :h, :r) RETURNING id"),
        {"u": user_id, "h": household_id, "r": role},
    ).scalar_one()


def mk_receipt(conn, household_id, currency="CNY", total="10.00"):
    return conn.execute(
        text("INSERT INTO receipts (household_id, image_url, total_amount,"
             " currency) VALUES (:h, '/x.jpg', :t, :c) RETURNING id"),
        {"h": household_id, "t": total, "c": currency},
    ).scalar_one()


def mk_recipe(conn, author_id):
    return conn.execute(
        text("INSERT INTO community_recipes (author_id, title)"
             " VALUES (:a, 'Test Recipe') RETURNING id"),
        {"a": author_id},
    ).scalar_one()


def mk_inventory(conn, household_id, currency="CNY", quantity="1.00"):
    return conn.execute(
        text("INSERT INTO inventory_items (household_id, raw_name, quantity,"
             " unit, currency) VALUES (:h, 'Milk', :q, 'bottle', :c)"
             " RETURNING id"),
        {"h": household_id, "q": quantity, "c": currency},
    ).scalar_one()


# -- tests ----------------------------------------------------------------

def test_receipt_currency_check_rejects_invalid(conn):
    """P2-06: receipts currency CHECK accepts USD, rejects an invalid code."""
    household_id = mk_household(conn)
    mk_receipt(conn, household_id, currency="USD")
    assert conn.execute(text("SELECT count(*) FROM receipts")).scalar() == 1
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            mk_receipt(conn, household_id, currency="XXX")
    # Rolls back cleanly: connection usable, only the USD receipt persisted.
    assert conn.execute(text("SELECT count(*) FROM receipts")).scalar() == 1


def test_inventory_currency_check_rejects_invalid(conn):
    """P2-06: inventory currency CHECK accepts USD, rejects an invalid code."""
    household_id = mk_household(conn)
    mk_inventory(conn, household_id, currency="USD")
    assert conn.execute(
        text("SELECT count(*) FROM inventory_items")).scalar() == 1
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            mk_inventory(conn, household_id, currency="XXX")
    assert conn.execute(
        text("SELECT count(*) FROM inventory_items")).scalar() == 1


def test_recipe_ingredient_unit_not_null(conn):
    user_id = mk_user(conn)
    recipe_id = mk_recipe(conn, user_id)
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                text("INSERT INTO recipe_ingredients (recipe_id, raw_name)"
                     " VALUES (:r, 'Rice')"),
                {"r": recipe_id},
            )
    assert conn.execute(
        text("SELECT count(*) FROM recipe_ingredients")).scalar() == 0


def test_duplicate_household_member_rejected(conn):
    user_id = mk_user(conn)
    household_id = mk_household(conn)
    add_member(conn, user_id, household_id)
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            add_member(conn, user_id, household_id)
    assert conn.execute(
        text("SELECT count(*) FROM household_members")).scalar() == 1


def test_duplicate_receipt_line_no_rejected(conn):
    household_id = mk_household(conn)
    receipt_id = mk_receipt(conn, household_id)
    conn.execute(
        text("INSERT INTO receipt_lines (receipt_id, line_no, raw_name,"
             " quantity, unit, price, currency)"
             " VALUES (:r, 1, 'Milk', 1, 'bottle', 5.00, 'CNY')"),
        {"r": receipt_id},
    )
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                text("INSERT INTO receipt_lines (receipt_id, line_no,"
                     " raw_name, quantity, unit, price, currency)"
                     " VALUES (:r, 1, 'Bread', 1, 'loaf', 3.00, 'CNY')"),
                {"r": receipt_id},
            )
    assert conn.execute(
        text("SELECT count(*) FROM receipt_lines")).scalar() == 1


def test_second_owner_rejected(conn):
    owner_id = mk_user(conn, phone="13800000001")
    second_id = mk_user(conn, phone="13800000002")
    household_id = mk_household(conn)
    add_member(conn, owner_id, household_id, role="owner")
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            add_member(conn, second_id, household_id, role="owner")
    assert conn.execute(
        text("SELECT count(*) FROM household_members"
             " WHERE household_id = :h AND role = 'owner'"),
        {"h": household_id},
    ).scalar() == 1


@pytest.mark.parametrize("stars", [0, 6])
def test_recipe_stars_range_rejected(conn, stars):
    user_id = mk_user(conn)
    recipe_id = mk_recipe(conn, user_id)
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                text("INSERT INTO recipe_ratings (recipe_id, user_id, stars)"
                     " VALUES (:r, :u, :s)"),
                {"r": recipe_id, "u": user_id, "s": stars},
            )
    assert conn.execute(
        text("SELECT count(*) FROM recipe_ratings")).scalar() == 0


def test_numeric_quantity_accepts_half(conn):
    household_id = mk_household(conn)
    item_id = mk_inventory(conn, household_id, quantity="0.5")
    stored = conn.execute(
        text("SELECT quantity FROM inventory_items WHERE id = :i"),
        {"i": item_id},
    ).scalar_one()
    assert stored == Decimal("0.50")
