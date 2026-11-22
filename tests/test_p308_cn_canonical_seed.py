"""P3-08 migration 0010: Chinese canonical seed + backfill.

Covers: the 0010 migration is the alembic head, the 21 Chinese
canonical ingredients + 39 aliases are seeded (with the expected
category / zone / shelf life, mirroring the 0002 Vietnamese analogues),
the backfill assigns canonical_ingredient_id to Chinese
recipe_ingredients rows (exact, alias, variant alias and
prefix-with-suffix raw_names; one-off raw_names stay NULL), the
backfill agrees with app.reconcile.resolve_canonical, and
?ingredient=五花肉 / 排骨 / 姜 return the Chinese recipes.

Runs against the disposable ``imsf_test`` database (same pattern as
test_phase3_recipes.py). The backfill is exercised end-to-end through
alembic: the fixture downgrades to 0008, inserts Chinese recipes with
canonical NULL (as if imported before the seed existed), upgrades to
head, and asserts. Fixture data is deleted in teardown; the test DB is
left at head. The 20 Vietnamese canonicals and the 10 brand aliases
are untouched by the migration.

NOTE on ordering: this module downgrades the shared imsf_test DB to
0008 and back. Alphabetical order puts test_p308 before
test_phase3_*, which rely on the 0010 seed, and pytest runs modules
sequentially here -- do not run this module concurrently with other
DB tests.
"""

import os
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
import sqlalchemy as sa
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- env for the app under test (must be set before importing app) -------
os.environ.setdefault("IMSF_SERVICE_TOKEN", "test-service-token")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

BASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://imsf:imsf@127.0.0.1:55434/imsf",
)
TEST_DB = "imsf_test"


def _test_url() -> str:
    url = urlparse(BASE_URL)
    return urlunparse(url._replace(path=f"/{TEST_DB}"))


os.environ["DATABASE_URL"] = _test_url()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.reconcile import normalize_name, resolve_canonical  # noqa: E402

client = TestClient(app)

TRUNCATE_SQL = (
    "TRUNCATE recipe_likes, saved_recipes, recipe_comments,"
    " transactions, shopping_lists, shopping_list_items,"
    " notifications, equipment_maintenance_logs,"
    " knowledge_documents, inventory_items, receipt_lines,"
    " receipts, equipments, community_recipes, recipe_ingredients,"
    " household_members, households, users"
    " RESTART IDENTITY CASCADE"
)

# --- expected seed (independent ground truth, from the live-DB analysis) ---
# (canonical_name, category, default_storage_zone, default_shelf_life_days)
EXPECTED_CANONICALS = [
    ("盐", "gia vị", "pantry", 365),
    ("料酒", "gia vị", "pantry", 365),
    ("姜", "gia vị", "fridge", 14),
    ("葱", "rau", "fridge", 7),
    ("生抽", "gia vị", "pantry", 180),
    ("蒜", "gia vị", "pantry", 60),
    ("油", "gia vị", "pantry", 365),
    ("冰糖", "gia vị", "pantry", 365),
    ("白糖", "gia vị", "pantry", 365),
    ("八角", "gia vị", "pantry", 365),
    ("酱油", "gia vị", "pantry", 180),
    ("淀粉", "đồ khô", "pantry", 180),
    ("胡椒粉", "gia vị", "pantry", 365),
    ("干辣椒", "gia vị", "pantry", 365),
    ("老抽", "gia vị", "pantry", 180),
    ("花椒", "gia vị", "pantry", 365),
    ("水", "đồ uống", "pantry", 365),
    ("排骨", "thịt", "fridge", 3),
    ("鸡精", "gia vị", "pantry", 365),
    ("醋", "gia vị", "pantry", 365),
    ("五花肉", "thịt", "fridge", 3),
]

# (alias, canonical_name) -- 28 plan aliases + 11 live-DB variant aliases.
EXPECTED_ALIASES = [
    ("食盐", "盐"),
    ("生姜", "姜"), ("姜片", "姜"),
    ("大葱", "葱"), ("香葱", "葱"), ("小葱", "葱"),
    ("葱花", "葱"), ("葱段", "葱"),
    ("大蒜", "蒜"), ("蒜瓣", "蒜"),
    ("食用油", "油"), ("花生油", "油"), ("菜籽油", "油"),
    ("植物油", "油"), ("橄榄油", "油"), ("香油", "油"), ("麻油", "油"),
    ("糖", "白糖"),
    ("大料", "八角"),
    ("鲜酱油", "酱油"), ("黄豆酱油", "酱油"),
    ("生粉", "淀粉"), ("玉米淀粉", "淀粉"), ("红薯淀粉", "淀粉"),
    ("水淀粉", "淀粉"),
    ("白胡椒粉", "胡椒粉"), ("黑胡椒粉", "胡椒粉"),
    ("干红辣椒", "干辣椒"), ("红辣椒", "干辣椒"), ("辣椒", "干辣椒"),
    ("清水", "水"), ("开水", "水"), ("温水", "水"), ("热水", "水"),
    ("味精", "鸡精"),
    ("白醋", "醋"), ("陈醋", "醋"), ("米醋", "醋"), ("香醋", "醋"),
]

# Fixture recipes: (title, slug, [(raw_name, expected_canonical_or_None)])
FIXTURE_RECIPES = [
    ("红烧肉测试", "test-p308-hongshaorou", [
        ("五花肉", "五花肉"),   # exact
        ("生姜", "姜"),         # plan alias
        ("冰糖", "冰糖"),       # exact
        ("老抽", "老抽"),       # exact
        ("黄酒", None),         # distinct wine, stays NULL
    ]),
    ("排骨汤测试", "test-p308-paigutang", [
        ("排骨", "排骨"),       # exact
        ("姜片", "姜"),         # variant alias
        ("葱花", "葱"),         # plan alias
        ("小葱末", "葱"),       # prefix: alias 小葱 opens 小葱末
        ("香叶", None),         # one-off, stays NULL
    ]),
    ("蒜蓉菜心测试", "test-p308-suanrong", [
        ("蒜瓣", "蒜"),         # variant alias
        ("植物油", "油"),       # variant alias
        ("盐", "盐"),           # exact
        ("水淀粉", "淀粉"),     # variant alias
        ("辣椒粉", "干辣椒"),   # prefix: alias 辣椒 opens 辣椒粉
        ("洋葱", None),         # not seeded, stays NULL
    ]),
]


def _alembic_cfg():
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


@pytest.fixture(scope="module", autouse=True)
def test_db():
    from alembic import command

    admin = sa.create_engine(BASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB},
        ).first()
        if not exists:
            conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    command.upgrade(_alembic_cfg(), "head")
    engine = sa.create_engine(_test_url())
    with engine.begin() as conn:
        conn.execute(text(TRUNCATE_SQL))
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def cn_seed_db(test_db):
    """End-to-end backfill: downgrade to 0008, insert Chinese recipes
    with canonical NULL, upgrade to head (0010 seeds + backfills)."""
    from alembic import command

    cfg = _alembic_cfg()
    command.downgrade(cfg, "0008")
    recipe_ids = []
    with test_db.begin() as conn:
        for title, slug, lines in FIXTURE_RECIPES:
            rid = uuid.uuid4()
            recipe_ids.append(rid)
            conn.execute(
                text(
                    "INSERT INTO community_recipes"
                    " (id, author_id, title, steps_json, status,"
                    "  source_url, language, slug)"
                    " VALUES (:id, NULL, :t, CAST('[]' AS jsonb),"
                    "  'published', :src, 'zh', :slug)"
                ),
                {"id": rid, "t": title,
                 "src": f"https://example.test/{slug}", "slug": slug},
            )
            for raw_name, _expected in lines:
                conn.execute(
                    text(
                        "INSERT INTO recipe_ingredients"
                        " (recipe_id, canonical_ingredient_id, raw_name,"
                        "  amount, unit, is_main_ingredient)"
                        " VALUES (:rid, NULL, :raw, NULL, '', FALSE)"
                    ),
                    {"rid": rid, "raw": raw_name},
                )
    command.upgrade(cfg, "head")
    yield test_db, recipe_ids
    with test_db.begin() as conn:
        conn.execute(
            text("DELETE FROM community_recipes WHERE id = ANY(:ids)"),
            {"ids": recipe_ids},
        )


def _canonical_name(engine, ingredient_id):
    if ingredient_id is None:
        return None
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT canonical_name FROM master_ingredients"
                 " WHERE id = :i"),
            {"i": ingredient_id},
        ).scalar_one()


# --- migration gate ----------------------------------------------------------

def test_migration_0010_is_head(test_db):
    with test_db.connect() as conn:
        version = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert version == "0010"


def test_seed_21_cn_ingredients(test_db):
    with test_db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT canonical_name, category,"
                " default_storage_zone, default_shelf_life_days"
                " FROM master_ingredients"
                " WHERE canonical_name = ANY(:names)"
                " ORDER BY canonical_name"
            ),
            {"names": [n for n, _, _, _ in EXPECTED_CANONICALS]},
        ).fetchall()
    assert len(rows) == 21
    assert sorted(rows) == sorted(EXPECTED_CANONICALS)
    with test_db.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM master_ingredients")
        ).scalar_one()
    # 20 Vietnamese (0002) + 21 Chinese (0010).
    assert total == 41


def test_seed_39_aliases(test_db):
    with test_db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT a.alias, m.canonical_name"
                " FROM master_ingredient_aliases a"
                " JOIN master_ingredients m"
                " ON m.id = a.master_ingredient_id"
                " WHERE m.canonical_name = ANY(:names)"
            ),
            {"names": [n for n, _, _, _ in EXPECTED_CANONICALS]},
        ).fetchall()
    assert sorted(rows) == sorted(EXPECTED_ALIASES)
    # The 10 brand aliases (0004) are untouched.
    with test_db.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM master_ingredient_aliases")
        ).scalar_one()
    assert total == 10 + 39


# --- backfill ------------------------------------------------------------------

def test_backfill_assigns_canonical(cn_seed_db):
    engine, recipe_ids = cn_seed_db
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT r.slug, ri.raw_name, ri.canonical_ingredient_id"
                " FROM recipe_ingredients ri"
                " JOIN community_recipes r ON r.id = ri.recipe_id"
                " WHERE r.id = ANY(:ids)"
            ),
            {"ids": recipe_ids},
        ).fetchall()
    expected = {}
    for _title, slug, lines in FIXTURE_RECIPES:
        for raw_name, canon in lines:
            expected[(slug, raw_name)] = canon
    assert len(rows) == sum(len(l) for _, _, l in FIXTURE_RECIPES)
    for slug, raw_name, ingredient_id in rows:
        assert _canonical_name(engine, ingredient_id) == \
            expected[(slug, raw_name)], (slug, raw_name)


def test_backfill_matches_resolve_canonical(cn_seed_db):
    """The migration's inline resolution agrees with the app's
    resolve_canonical on every backfilled row. (The maps are built
    here with the same queries as worker.main.load_master_map /
    load_alias_map -- worker.main itself is not imported, it pulls
    redis/qwen/rag.)"""
    engine, recipe_ids = cn_seed_db
    with engine.begin() as conn:
        master_rows = conn.execute(
            text("SELECT id, canonical_name, default_storage_zone,"
                 " default_shelf_life_days FROM master_ingredients")
        ).all()
        master_map = {
            normalize_name(r[1]): {"id": r[0], "name": r[1],
                                   "zone": r[2], "shelf_life": r[3]}
            for r in master_rows
        }
        by_id = {e["id"]: e for e in master_map.values()}
        alias_rows = conn.execute(
            text("SELECT alias, master_ingredient_id"
                 " FROM master_ingredient_aliases")
        ).all()
        alias_map = {}
        for alias, ingredient_id in alias_rows:
            entry = by_id.get(ingredient_id)
            if entry is not None:
                alias_map[normalize_name(alias)] = entry
        rows = conn.execute(
            text(
                "SELECT ri.raw_name, ri.canonical_ingredient_id"
                " FROM recipe_ingredients ri"
                " WHERE ri.recipe_id = ANY(:ids)"
            ),
            {"ids": recipe_ids},
        ).fetchall()
    for raw_name, ingredient_id in rows:
        entry = resolve_canonical(raw_name, None, master_map,
                                  alias_map=alias_map)
        expected_id = entry["id"] if entry is not None else None
        assert ingredient_id == expected_id, raw_name


def test_backfill_is_idempotent(cn_seed_db):
    """Re-running the backfill UPDATE (NULL rows only) changes nothing:
    no row is double-assigned and no NULL row gains a canonical."""
    from alembic import command

    engine, recipe_ids = cn_seed_db
    with engine.connect() as conn:
        before_rows = conn.execute(
            text(
                "SELECT ri.raw_name, m.canonical_name"
                " FROM recipe_ingredients ri"
                " LEFT JOIN master_ingredients m"
                " ON m.id = ri.canonical_ingredient_id"
                " WHERE ri.recipe_id = ANY(:ids)"
                " ORDER BY ri.raw_name"
            ),
            {"ids": recipe_ids},
        ).fetchall()
    before = [(raw, canon) for raw, canon in before_rows]
    # Downgrade + upgrade again: the seed is re-inserted (ON CONFLICT
    # DO NOTHING) and the backfill re-runs over the NULL rows only.
    # The re-seed mints NEW ingredient uuids, so compare by canonical
    # NAME, not by id.
    command.downgrade(_alembic_cfg(), "0008")
    command.upgrade(_alembic_cfg(), "head")
    with engine.connect() as conn:
        after_rows = conn.execute(
            text(
                "SELECT ri.raw_name, m.canonical_name"
                " FROM recipe_ingredients ri"
                " LEFT JOIN master_ingredients m"
                " ON m.id = ri.canonical_ingredient_id"
                " WHERE ri.recipe_id = ANY(:ids)"
                " ORDER BY ri.raw_name"
            ),
            {"ids": recipe_ids},
        ).fetchall()
    after = [(raw, canon) for raw, canon in after_rows]
    assert before == after


# --- API -----------------------------------------------------------------------

def test_ingredient_filter_finds_cn_recipes(cn_seed_db):
    engine, recipe_ids = cn_seed_db
    by_slug = {slug: title
               for title, slug, _ in FIXTURE_RECIPES}
    cases = [
        ("五花肉", ["test-p308-hongshaorou"]),
        ("排骨", ["test-p308-paigutang"]),
        ("姜", ["test-p308-hongshaorou", "test-p308-paigutang"]),
        ("葱", ["test-p308-paigutang"]),
        ("油", ["test-p308-suanrong"]),
        ("香叶", []),   # one-off, never seeded
        ("黄酒", []),   # distinct wine, never seeded
    ]
    for ingredient, expected_slugs in cases:
        r = client.get("/api/v2/recipes",
                       params={"ingredient": ingredient})
        assert r.status_code == 200, r.text
        got = {item["slug"] for item in r.json()["items"]}
        assert got == set(expected_slugs), ingredient
        for slug in expected_slugs:
            assert by_slug[slug]  # fixture slug is known
