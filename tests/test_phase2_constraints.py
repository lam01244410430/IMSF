"""Constraint tests for the Phase 2 migrations (design §3/§4).

Runs against a disposable ``imsf_v2_test`` database on the same Postgres
server as DATABASE_URL, so the dev ``imsf_v2`` data is never touched.
The fixture creates the test DB if missing and runs ``alembic upgrade
head`` against it, so the tests verify the real migrations, not a copy.

DATABASE_URL defaults to the CI service URL (postgres:16, user imsf_v2)
when unset, matching .github/workflows/ci.yml.

Covers the Phase 2 Step 1 gate (design §4): one transaction per receipt
(§3.1), one open shopping list per household (§3.2), one open
lazy_tracking notification per item (§3.4), the transactions currency
CHECK (§3.1), NUMERIC(10,2) fractions (§2), the pgvector extension and
1024-dim embedding (§3.7, D3), and the 0004 alias seeds (§3.6/§4).

NOTE: "cost without currency must fail" is deliberately NOT tested at
the DB level — the design (§3.5) leaves that CHECK to the application
layer (Gate D), so the DB permits it by design.
"""

import itertools
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
    "postgresql+psycopg://imsf_v2:imsf_v2@127.0.0.1:5432/imsf_v2"
)
TEST_DB = "imsf_v2_test"

_phone_seq = itertools.count(1)


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

def mk_user(conn):
    phone = f"13900000{next(_phone_seq):03d}"
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


def mk_receipt(conn, household_id, currency="CNY", total="10.00"):
    return conn.execute(
        text("INSERT INTO receipts (household_id, image_url, total_amount,"
             " currency) VALUES (:h, '/x.jpg', :t, :c) RETURNING id"),
        {"h": household_id, "t": total, "c": currency},
    ).scalar_one()


def mk_inventory(conn, household_id, currency="CNY", quantity="1.00"):
    return conn.execute(
        text("INSERT INTO inventory_items (household_id, raw_name, quantity,"
             " unit, currency) VALUES (:h, 'Milk', :q, 'bottle', :c)"
             " RETURNING id"),
        {"h": household_id, "q": quantity, "c": currency},
    ).scalar_one()


def mk_transaction(conn, household_id, receipt_id=None, amount="10.00",
                   currency="CNY"):
    return conn.execute(
        text("INSERT INTO transactions (household_id, receipt_id, type,"
             " amount, currency, category, occurred_at)"
             " VALUES (:h, :r, 'expense', :a, :c, 'food', now())"
             " RETURNING id"),
        {"h": household_id, "r": receipt_id, "a": amount, "c": currency},
    ).scalar_one()


def mk_shopping_list(conn, household_id):
    return conn.execute(
        text("INSERT INTO shopping_lists (household_id)"
             " VALUES (:h) RETURNING id"),
        {"h": household_id},
    ).scalar_one()


def mk_notification(conn, user_id, household_id, ntype, ref_type, ref_id,
                    status="sent"):
    return conn.execute(
        text("INSERT INTO notifications (user_id, household_id, type,"
             " ref_type, ref_id, payload_json, status)"
             " VALUES (:u, :h, :t, :rt, :ri, '{}'::jsonb, :s)"
             " RETURNING id"),
        {"u": user_id, "h": household_id, "t": ntype,
         "rt": ref_type, "ri": ref_id, "s": status},
    ).scalar_one()


def _vector_literal(n):
    return "[" + ",".join(["0.1"] * n) + "]"


def mk_knowledge_doc(conn, dims=1024):
    return conn.execute(
        text("INSERT INTO knowledge_documents (topic, source, content,"
             " embedding) VALUES ('shelf_life', 'test', 'test content',"
             " CAST(:emb AS vector)) RETURNING id"),
        {"emb": _vector_literal(dims)},
    ).scalar_one()


# -- tests ----------------------------------------------------------------

def test_one_transaction_per_receipt(conn):
    """§3.1: partial unique index — at most 1 transaction per receipt."""
    household_id = mk_household(conn)
    receipt_id = mk_receipt(conn, household_id)
    mk_transaction(conn, household_id, receipt_id=receipt_id)
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            mk_transaction(conn, household_id, receipt_id=receipt_id)
    assert conn.execute(
        text("SELECT count(*) FROM transactions"
             " WHERE receipt_id = :r"),
        {"r": receipt_id},
    ).scalar() == 1


def test_one_open_shopping_list_per_household(conn):
    """§3.2: partial unique index — at most 1 open list per household;
    a 'done' list must not block a new open one."""
    household_id = mk_household(conn)
    first_id = mk_shopping_list(conn, household_id)
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            mk_shopping_list(conn, household_id)
    assert conn.execute(
        text("SELECT count(*) FROM shopping_lists"
             " WHERE household_id = :h AND status = 'open'"),
        {"h": household_id},
    ).scalar() == 1
    # Mark the first list done: a new open list must now succeed.
    conn.execute(
        text("UPDATE shopping_lists SET status = 'done',"
             " completed_at = now() WHERE id = :i"),
        {"i": first_id},
    )
    mk_shopping_list(conn, household_id)
    assert conn.execute(
        text("SELECT count(*) FROM shopping_lists"
             " WHERE household_id = :h AND status = 'open'"),
        {"h": household_id},
    ).scalar() == 1


def test_one_open_lazy_tracking_per_item(conn):
    """§3.4: partial unique index — at most 1 open lazy_tracking
    notification per item; a maintenance_reminder for the same ref
    does NOT conflict (different type, separate index)."""
    user_id = mk_user(conn)
    household_id = mk_household(conn)
    item_id = mk_inventory(conn, household_id)
    mk_notification(conn, user_id, household_id, "lazy_tracking",
                    "inventory_item", item_id, status="sent")
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            mk_notification(conn, user_id, household_id, "lazy_tracking",
                            "inventory_item", item_id, status="sent")
    assert conn.execute(
        text("SELECT count(*) FROM notifications"
             " WHERE type = 'lazy_tracking' AND ref_type = 'inventory_item'"
             " AND ref_id = :i AND status IN ('sent','delivered','read')"),
        {"i": item_id},
    ).scalar() == 1
    # Same ref, different notification type: must succeed.
    mk_notification(conn, user_id, household_id, "maintenance_reminder",
                    "inventory_item", item_id, status="sent")
    assert conn.execute(
        text("SELECT count(*) FROM notifications"
             " WHERE type = 'maintenance_reminder'"
             " AND ref_type = 'inventory_item' AND ref_id = :i"),
        {"i": item_id},
    ).scalar() == 1


def test_transactions_currency_check(conn):
    """§3.1 (P2-06): currency CHECK accepts the 14 supported currencies
    and rejects anything outside them."""
    household_id = mk_household(conn)
    for cur in ("CNY", "VND", "USD", "EUR", "HKD", "THB", "MYR", "SGD",
                "IDR", "PHP", "KHR", "LAK", "MMK", "BND"):
        mk_transaction(conn, household_id, currency=cur)
    assert conn.execute(
        text("SELECT count(*) FROM transactions")).scalar() == 14
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            mk_transaction(conn, household_id, currency="XXX")
    assert conn.execute(
        text("SELECT count(*) FROM transactions")).scalar() == 14


def test_all_currency_checks_accept_new_currencies(conn):
    """P2-06: the other currency CHECKs (receipts, inventory_items,
    households) accept a new currency and reject an invalid code.
    (receipt_lines + maintenance_logs share the same CHECK pattern and
    are verified by the 0005 migration gate.)"""
    household_id = mk_household(conn)
    mk_receipt(conn, household_id, currency="USD")
    mk_inventory(conn, household_id, currency="EUR")
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            mk_receipt(conn, household_id, currency="XXX")
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            mk_inventory(conn, household_id, currency="XXX")
    conn.execute(
        text("INSERT INTO households (name, default_currency)"
             " VALUES ('USD Home', 'USD')"))
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                text("INSERT INTO households (name, default_currency)"
                     " VALUES ('Bad Home', 'XXX')"))


def test_numeric_accepts_fraction(conn):
    """§2: NUMERIC(10,2) accepts 0.5 and stores it as 0.50."""
    household_id = mk_household(conn)
    list_id = mk_shopping_list(conn, household_id)
    item_id = conn.execute(
        text("INSERT INTO shopping_list_items (shopping_list_id, raw_name,"
             " amount, unit) VALUES (:l, 'Milk', :a, 'bottle')"
             " RETURNING id"),
        {"l": list_id, "a": "0.5"},
    ).scalar_one()
    stored_item = conn.execute(
        text("SELECT amount FROM shopping_list_items WHERE id = :i"),
        {"i": item_id},
    ).scalar_one()
    assert stored_item == Decimal("0.50")
    txn_id = mk_transaction(conn, household_id, amount="0.5")
    stored_txn = conn.execute(
        text("SELECT amount FROM transactions WHERE id = :i"),
        {"i": txn_id},
    ).scalar_one()
    assert stored_txn == Decimal("0.50")


def test_pgvector_extension_and_1024_dim(conn):
    """§3.7 / D3: pgvector extension installed; embedding accepts a
    1024-dim vector and rejects a 1023-dim one."""
    ext_count = conn.execute(
        text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'"),
    ).scalar()
    assert ext_count == 1
    doc_id = mk_knowledge_doc(conn, dims=1024)
    stored = conn.execute(
        text("SELECT embedding FROM knowledge_documents WHERE id = :i"),
        {"i": doc_id},
    ).scalar_one()
    assert stored is not None
    # Wrong dimension: pgvector raises a data error (not IntegrityError),
    # so accept any SQLAlchemy DB error here.
    with pytest.raises(sa.exc.SQLAlchemyError):
        with conn.begin_nested():
            mk_knowledge_doc(conn, dims=1023)
    assert conn.execute(
        text("SELECT count(*) FROM knowledge_documents")).scalar() == 1


def test_alias_seed_present(conn):
    """§3.6/§4 (migration 0004): at least 10 seeded aliases, and
    '农夫山泉' resolves to the master ingredient 'Nước suối'."""
    count = conn.execute(
        text("SELECT count(*) FROM master_ingredient_aliases"),
    ).scalar()
    assert count >= 10
    canonical = conn.execute(
        text("SELECT mi.canonical_name FROM master_ingredient_aliases a"
             " JOIN master_ingredients mi"
             " ON mi.id = a.master_ingredient_id"
             " WHERE a.alias = '农夫山泉'"),
    ).scalar_one()
    assert canonical == "Nước suối"
