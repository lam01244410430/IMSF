"""Phase 3 recipe blog tests (reform plan SS6).

Covers: list (empty + seeded rows, published-only, author null,
pagination + 400s), detail (full shape, 404 for missing/draft),
ingredient search filter (canonical join only -- a raw-name-only
line NEVER matches), like/unlike idempotency + likes_count updates,
save/unsave idempotency, auth-required 401s, anonymous list (no
liked/saved keys), authenticated list flags, the 0008 migration
gate on the disposable DB, and the 0008 columns (new fields in list
+ detail, ?language= / ?category= filters, blank filter -> 400).

Runs against the disposable ``imsf_test`` database (same pattern as
the Step 2/3/4 and email-auth test files) so the dev DB is never
touched. Recipes are seeded in the TEST db only, never in live.
"""

import json
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

from app.auth import mint_access_token  # noqa: E402
from app.main import app  # noqa: E402

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


@pytest.fixture(scope="module", autouse=True)
def test_db():
    from alembic import command
    from alembic.config import Config

    admin = sa.create_engine(BASE_URL, isolation_level="AUTOCOMMIT")
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
    command.upgrade(cfg, "head")
    engine = sa.create_engine(_test_url())
    with engine.begin() as conn:
        conn.execute(text(TRUNCATE_SQL))
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine(test_db):
    yield test_db
    with test_db.begin() as conn:
        conn.execute(text(TRUNCATE_SQL))


# --- helpers ---------------------------------------------------------------

def mk_user(db_engine, name, phone="13800001111"):
    user_id = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, phone, name)"
                 " VALUES (:id, :p, :n)"),
            {"id": user_id, "p": phone, "n": name},
        )
    return user_id


def auth_headers(user_id):
    return {"Authorization": f"Bearer {mint_access_token(user_id)}"}


def seed_recipe(db_engine, author_id, title, status="published",
                cook_time=30, steps=None, cover_image=None,
                description=None, source_url=None, category=None,
                language=None, difficulty=None, taste=None, slug=None,
                author_name=None):
    recipe_id = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO community_recipes"
                 " (id, author_id, title, cover_image, steps_json,"
                 "  cook_time, status, description, source_url,"
                 "  category, language, difficulty, taste, slug, author)"
                 " VALUES (:id, :aid, :t, :cover,"
                 "  CAST(:steps AS jsonb), :ct, :s, :desc, :src,"
                 "  :cat, :lang, :diff, :taste, :slug, :aname)"),
            {"id": recipe_id, "aid": author_id, "t": title,
             "cover": cover_image,
             "steps": json.dumps(steps if steps is not None
                                 else ["Bước 1", "Bước 2"]),
             "ct": cook_time, "s": status, "desc": description,
             "src": source_url, "cat": category, "lang": language,
             "diff": difficulty, "taste": taste, "slug": slug,
             "aname": author_name},
        )
    return recipe_id


def add_ingredient(db_engine, recipe_id, canonical_name, raw_name,
                   amount, unit):
    canonical_id = None
    if canonical_name is not None:
        with db_engine.connect() as conn:
            canonical_id = conn.execute(
                text("SELECT id FROM master_ingredients"
                     " WHERE canonical_name = :n"),
                {"n": canonical_name},
            ).scalar_one_or_none()
        assert canonical_id is not None, (
            f"seed canonical ingredient missing: {canonical_name!r}")
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO recipe_ingredients"
                 " (recipe_id, canonical_ingredient_id, raw_name,"
                 "  amount, unit)"
                 " VALUES (:rid, :cid, :raw, :amt, :unit)"),
            {"rid": recipe_id, "cid": canonical_id, "raw": raw_name,
             "amt": amount, "unit": unit},
        )


def get_likes_count(db_engine, recipe_id):
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT likes_count FROM community_recipes"
                 " WHERE id = :rid"),
            {"rid": recipe_id},
        ).scalar_one()


def count_rows(db_engine, table, recipe_id, user_id):
    with db_engine.connect() as conn:
        return conn.execute(
            text(f"SELECT COUNT(*) FROM {table}"
                 " WHERE recipe_id = :rid AND user_id = :uid"),
            {"rid": recipe_id, "uid": user_id},
        ).scalar_one()


# --- migration gate ----------------------------------------------------------

def test_migration_0009_is_head(db_engine):
    with db_engine.connect() as conn:
        version = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        assert version == "0009"
        for table in ("recipe_likes", "saved_recipes"):
            exists = conn.execute(
                text("SELECT 1 FROM information_schema.tables"
                     " WHERE table_name = :t"),
                {"t": table},
            ).first()
            assert exists is not None, f"{table} missing"
            uq = conn.execute(
                text("SELECT 1 FROM information_schema.table_constraints"
                     " WHERE table_name = :t"
                     " AND constraint_type = 'UNIQUE'"),
                {"t": table},
            ).first()
            assert uq is not None, f"{table} has no UNIQUE constraint"
        # 0008 columns: all nullable TEXT, no defaults.
        cols = conn.execute(
            text("SELECT column_name, is_nullable, column_default"
                 " FROM information_schema.columns"
                 " WHERE table_name = 'community_recipes'"
                 " AND column_name IN ('description', 'source_url',"
                 "  'category', 'language', 'difficulty', 'taste',"
                 "  'slug', 'author')"),
        ).all()
        assert {c[0] for c in cols} == {
            "description", "source_url", "category", "language",
            "difficulty", "taste", "slug", "author",
        }
        assert all(c[1] == "YES" and c[2] is None for c in cols)


# --- list --------------------------------------------------------------------

def test_list_empty_anonymous(db_engine):
    r = client.get("/api/v2/recipes")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_list_seeded_published_only(db_engine):
    author = mk_user(db_engine, "Đầu bếp A")
    r1 = seed_recipe(db_engine, author, "Canh trứng cà chua")
    r2 = seed_recipe(db_engine, author, "Cơm gà", cook_time=45)
    seed_recipe(db_engine, author, "Nháp chưa xong", status="draft")
    add_ingredient(db_engine, r1, "Trứng gà", "trứng gà ta", 2, "quả")
    add_ingredient(db_engine, r1, "Cà chua", "cà chua", 3, "quả")
    add_ingredient(db_engine, r2, "Thịt gà", "thịt gà", 0.5, "kg")
    r = client.get("/api/v2/recipes")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[str(r1)]["ingredient_count"] == 2
    assert by_id[str(r1)]["likes_count"] == 0
    assert by_id[str(r1)]["cook_time"] == 30
    assert by_id[str(r1)]["author"] == {"id": str(author),
                                        "name": "Đầu bếp A"}
    assert by_id[str(r2)]["ingredient_count"] == 1
    # No servings key anywhere: the column does not exist.
    assert "servings" not in by_id[str(r1)]
    # Anonymous: no liked/saved keys at all.
    assert "liked" not in by_id[str(r1)]
    assert "saved" not in by_id[str(r1)]


def test_list_author_null(db_engine):
    r1 = seed_recipe(db_engine, None, "Món vô danh")
    r = client.get("/api/v2/recipes")
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["author"] is None
    assert r.json()["items"][0]["id"] == str(r1)


def test_list_pagination_and_validation(db_engine):
    author = mk_user(db_engine, "Đầu bếp B")
    ids = [seed_recipe(db_engine, author, f"Món {i}")
           for i in range(3)]
    r = client.get("/api/v2/recipes", params={"limit": 2, "offset": 0})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 3
    assert len(r.json()["items"]) == 2
    r = client.get("/api/v2/recipes", params={"limit": 2, "offset": 2})
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["id"] == str(ids[0])  # oldest last
    assert client.get("/api/v2/recipes",
                      params={"limit": 0}).status_code == 400
    assert client.get("/api/v2/recipes",
                      params={"limit": 101}).status_code == 400
    assert client.get("/api/v2/recipes",
                      params={"offset": -1}).status_code == 400


def test_list_author_filter(db_engine):
    a1 = mk_user(db_engine, "Tác giả 1", phone="13800002222")
    a2 = mk_user(db_engine, "Tác giả 2", phone="13800003333")
    seed_recipe(db_engine, a1, "Món của A1")
    seed_recipe(db_engine, a2, "Món của A2")
    r = client.get("/api/v2/recipes", params={"author": str(a1)})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["title"] == "Món của A1"


# --- ingredient search -------------------------------------------------------

def test_ingredient_filter_canonical_only(db_engine):
    author = mk_user(db_engine, "Đầu bếp C")
    with_egg = seed_recipe(db_engine, author, "Canh trứng")
    with_tomato = seed_recipe(db_engine, author, "Salad cà chua")
    raw_only = seed_recipe(db_engine, author, "Món trứng thô")
    add_ingredient(db_engine, with_egg, "Trứng gà", "trứng gà ta",
                   2, "quả")
    add_ingredient(db_engine, with_tomato, "Cà chua", "cà chua",
                   3, "quả")
    # Raw-name-only line: canonical_ingredient_id NULL, raw_name
    # literally "Trứng gà" -- must NOT match the canonical filter.
    add_ingredient(db_engine, raw_only, None, "Trứng gà", 1, "quả")

    r = client.get("/api/v2/recipes",
                   params={"ingredient": "Trứng gà"})
    assert r.status_code == 200, r.text
    assert [item["id"] for item in r.json()["items"]] == [str(with_egg)]

    r = client.get("/api/v2/recipes",
                   params={"ingredient": "Cà chua"})
    assert [item["id"] for item in r.json()["items"]] == [str(with_tomato)]

    r = client.get("/api/v2/recipes",
                   params={"ingredient": "Không có"})
    assert r.json() == {"items": [], "total": 0, "limit": 20,
                        "offset": 0}
    assert client.get("/api/v2/recipes",
                      params={"ingredient": "  "}).status_code == 400


# --- 0008 columns: new fields + language/category filters ----------------

def test_new_fields_in_list_and_detail(db_engine):
    author = mk_user(db_engine, "Đầu bếp J")
    rid = seed_recipe(
        db_engine, author, "Phở bò",
        description="Nước dùng trong, thơm quế hồi.",
        source_url="https://example.com/pho-bo",
        category="Món nước", language="vi", difficulty="vừa",
        taste="mặn", slug="pho-bo", author_name="Món Ngon Mỗi Ngày")
    # A recipe with no 0008 metadata: every new field is null, and
    # the existing `author` object (from author_id) is untouched.
    plain = seed_recipe(db_engine, author, "Món trơn")
    r = client.get("/api/v2/recipes")
    assert r.status_code == 200, r.text
    by_id = {item["id"]: item for item in r.json()["items"]}
    item = by_id[str(rid)]
    assert item["description"] == "Nước dùng trong, thơm quế hồi."
    assert item["source_url"] == "https://example.com/pho-bo"
    assert item["category"] == "Món nước"
    assert item["language"] == "vi"
    assert item["difficulty"] == "vừa"
    assert item["taste"] == "mặn"
    assert item["slug"] == "pho-bo"
    # TEXT author is `author_name`; `author` stays the {id, name} object.
    assert item["author_name"] == "Món Ngon Mỗi Ngày"
    assert item["author"] == {"id": str(author), "name": "Đầu bếp J"}
    plain_item = by_id[str(plain)]
    for key in ("description", "source_url", "category", "language",
                "difficulty", "taste", "slug", "author_name"):
        assert plain_item[key] is None, key

    r = client.get(f"/api/v2/recipes/{rid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["description"] == "Nước dùng trong, thơm quế hồi."
    assert body["category"] == "Món nước"
    assert body["language"] == "vi"
    assert body["slug"] == "pho-bo"
    assert body["author_name"] == "Món Ngon Mỗi Ngày"
    assert body["author"] == {"id": str(author), "name": "Đầu bếp J"}


def test_language_and_category_filters(db_engine):
    author = mk_user(db_engine, "Đầu bếp K")
    vi = seed_recipe(db_engine, author, "Canh chua",
                     language="vi", category="Món nước")
    zh = seed_recipe(db_engine, author, "番茄炒蛋",
                     language="zh", category="家常菜")
    other = seed_recipe(db_engine, author, "Salad",
                        language="vi", category="Món nguội")

    r = client.get("/api/v2/recipes", params={"language": "vi"})
    assert r.status_code == 200, r.text
    assert {i["id"] for i in r.json()["items"]} == {str(vi), str(other)}
    assert r.json()["total"] == 2

    r = client.get("/api/v2/recipes", params={"language": "zh"})
    assert [i["id"] for i in r.json()["items"]] == [str(zh)]

    r = client.get("/api/v2/recipes", params={"category": "Món nước"})
    assert [i["id"] for i in r.json()["items"]] == [str(vi)]

    # Filters compose.
    r = client.get("/api/v2/recipes",
                   params={"language": "vi", "category": "Món nguội"})
    assert [i["id"] for i in r.json()["items"]] == [str(other)]

    r = client.get("/api/v2/recipes", params={"language": "en"})
    assert r.json() == {"items": [], "total": 0, "limit": 20,
                        "offset": 0}

    # Blank filter values are 400, same contract as ?ingredient=.
    assert client.get("/api/v2/recipes",
                      params={"language": "  "}).status_code == 400
    assert client.get("/api/v2/recipes",
                      params={"category": ""}).status_code == 400


# --- detail ------------------------------------------------------------------

def test_detail_full_and_404(db_engine):
    author = mk_user(db_engine, "Đầu bếp D")
    rid = seed_recipe(db_engine, author, "Canh trứng cà chua",
                      steps=[{"text": "Đập trứng.", "image": None},
                             "Cho cà chua vào."])
    add_ingredient(db_engine, rid, "Trứng gà", "trứng gà ta", 2, "quả")
    add_ingredient(db_engine, rid, None, "Muối hột", None, "nhúm")
    draft = seed_recipe(db_engine, author, "Nháp", status="draft")

    r = client.get(f"/api/v2/recipes/{rid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Canh trứng cà chua"
    assert body["ingredients"] == [
        {"name": "Trứng gà", "quantity": 2.0, "unit": "quả"},
        {"name": "Muối hột", "quantity": None, "unit": "nhúm"},
    ]
    assert body["steps"] == [{"text": "Đập trứng.", "image": None},
                             {"text": "Cho cà chua vào.", "image": None}]
    assert body["comment_count"] == 0
    assert body["saved_count"] == 0
    assert body["created_at"] is not None
    assert body["author_recipe_count"] == 1
    assert body["ingredient_count"] == 2

    assert client.get(f"/api/v2/recipes/{uuid.uuid4()}").status_code == 404
    assert client.get(f"/api/v2/recipes/{draft}").status_code == 404


def test_detail_comment_count_real(db_engine):
    author = mk_user(db_engine, "Đầu bếp E")
    commenter = mk_user(db_engine, "Người bình luận",
                        phone="13800004444")
    rid = seed_recipe(db_engine, author, "Món có bình luận")
    with db_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO recipe_comments"
                 " (recipe_id, user_id, content)"
                 " VALUES (:rid, :uid, 'Ngon!')"),
            {"rid": rid, "uid": commenter},
        )
    r = client.get(f"/api/v2/recipes/{rid}")
    assert r.status_code == 200, r.text
    assert r.json()["comment_count"] == 1


# --- like / unlike -----------------------------------------------------------

def test_like_unlike_idempotent(db_engine):
    author = mk_user(db_engine, "Đầu bếp F")
    user = mk_user(db_engine, "Người thích", phone="13800005555")
    rid = seed_recipe(db_engine, author, "Món được thích")
    h = auth_headers(user)

    r = client.post(f"/api/v2/recipes/{rid}/like", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"id": str(rid), "likes_count": 1, "liked": True}
    assert get_likes_count(db_engine, rid) == 1
    assert count_rows(db_engine, "recipe_likes", rid, user) == 1

    # Second like: no-op, count stays 1.
    r = client.post(f"/api/v2/recipes/{rid}/like", headers=h)
    assert r.json() == {"id": str(rid), "likes_count": 1, "liked": True}
    assert get_likes_count(db_engine, rid) == 1
    assert count_rows(db_engine, "recipe_likes", rid, user) == 1

    r = client.post(f"/api/v2/recipes/{rid}/unlike", headers=h)
    assert r.json() == {"id": str(rid), "likes_count": 0, "liked": False}
    assert get_likes_count(db_engine, rid) == 0
    assert count_rows(db_engine, "recipe_likes", rid, user) == 0

    # Second unlike: no-op, count never goes below 0.
    r = client.post(f"/api/v2/recipes/{rid}/unlike", headers=h)
    assert r.json() == {"id": str(rid), "likes_count": 0, "liked": False}
    assert get_likes_count(db_engine, rid) == 0


def test_like_draft_404_and_auth_required(db_engine):
    author = mk_user(db_engine, "Đầu bếp G")
    user = mk_user(db_engine, "Người dùng", phone="13800006666")
    rid = seed_recipe(db_engine, author, "Món công khai")
    draft = seed_recipe(db_engine, author, "Nháp", status="draft")
    h = auth_headers(user)

    assert client.post(
        f"/api/v2/recipes/{draft}/like", headers=h).status_code == 404
    assert client.post(
        f"/api/v2/recipes/{uuid.uuid4()}/like",
        headers=h).status_code == 404
    for path in ("like", "unlike", "save", "unsave"):
        r = client.post(f"/api/v2/recipes/{rid}/{path}")
        assert r.status_code == 401, (path, r.text)


# --- save / unsave -----------------------------------------------------------

def test_save_unsave_idempotent(db_engine):
    author = mk_user(db_engine, "Đầu bếp H")
    user = mk_user(db_engine, "Người lưu", phone="13800007777")
    rid = seed_recipe(db_engine, author, "Món được lưu")
    h = auth_headers(user)

    r = client.post(f"/api/v2/recipes/{rid}/save", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"id": str(rid), "saved": True}
    assert count_rows(db_engine, "saved_recipes", rid, user) == 1

    r = client.post(f"/api/v2/recipes/{rid}/save", headers=h)
    assert r.json() == {"id": str(rid), "saved": True}
    assert count_rows(db_engine, "saved_recipes", rid, user) == 1

    r = client.post(f"/api/v2/recipes/{rid}/unsave", headers=h)
    assert r.json() == {"id": str(rid), "saved": False}
    assert count_rows(db_engine, "saved_recipes", rid, user) == 0

    r = client.post(f"/api/v2/recipes/{rid}/unsave", headers=h)
    assert r.json() == {"id": str(rid), "saved": False}
    assert count_rows(db_engine, "saved_recipes", rid, user) == 0


# --- authenticated list flags ------------------------------------------------

def test_authenticated_list_flags(db_engine):
    author = mk_user(db_engine, "Đầu bếp I")
    user = mk_user(db_engine, "Người đọc", phone="13800008888")
    r1 = seed_recipe(db_engine, author, "Món đã thích + lưu")
    r2 = seed_recipe(db_engine, author, "Món chưa chạm")
    h = auth_headers(user)
    client.post(f"/api/v2/recipes/{r1}/like", headers=h)
    client.post(f"/api/v2/recipes/{r1}/save", headers=h)

    r = client.get("/api/v2/recipes", headers=h)
    assert r.status_code == 200, r.text
    by_id = {item["id"]: item for item in r.json()["items"]}
    assert by_id[str(r1)]["liked"] is True
    assert by_id[str(r1)]["saved"] is True
    assert by_id[str(r1)]["likes_count"] == 1
    assert by_id[str(r2)]["liked"] is False
    assert by_id[str(r2)]["saved"] is False

    # Detail shows the same flags for the authenticated reader.
    r = client.get(f"/api/v2/recipes/{r1}", headers=h)
    assert r.json()["liked"] is True
    assert r.json()["saved"] is True
