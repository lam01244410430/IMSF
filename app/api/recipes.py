"""Recipe blog endpoints (reform plan SS6, Phase 3).

- GET /api/v2/recipes -- public list, paginated (limit default 20,
  max 100), optional ?ingredient=<canonical_name> (matches via
  recipe_ingredients.canonical_ingredient_id -> master_ingredients,
  NEVER on raw OCR strings), ?author=<user uuid>, ?language=<vi|zh|...>
  and ?category=<category>. Only status='published' recipes are
  listed. ``liked`` / ``saved`` are included ONLY when the request is
  authenticated (optional auth -- anonymous readers are never 401'd).
- GET /api/v2/recipes/{id} -- public detail: same fields + ingredients
  (canonical name + quantity + unit per line) + steps (parsed from
  steps_json) + comment_count (real count from recipe_comments) +
  saved_count (real count from saved_recipes) + author_recipe_count.
  404 when missing or not published.
- POST /{id}/like + /{id}/unlike, POST /{id}/save + /{id}/unsave --
  auth required, idempotent. like inserts (ON CONFLICT DO NOTHING) and
  increments community_recipes.likes_count by 1 ONLY when a new row
  was inserted; unlike deletes and decrements (never below 0, guarded
  by GREATEST). Same pattern for save/unsave on saved_recipes.

New fields (migration 0008): description, source_url, category,
language, difficulty, taste, slug and author (TEXT). The TEXT author
is the source's display name for the recipe (e.g. the site it was
scraped from); it is exposed as ``author_name`` in the JSON because
the ``author`` key is already the ``{id, name}`` object built from
``author_id`` (the users FK), and renaming that would break existing
clients. ``author_name`` is null when the column is null.

DEFERRED (plan SS6.4): posting a recipe, comments -- no endpoints
here. No ``servings`` field anywhere: community_recipes has no such
column, so none is fabricated.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from app.auth import Identity, optional_auth, require_auth
from app.db import get_engine

router = APIRouter(prefix="/api/v2/recipes", tags=["recipes"])

PUBLISHED = "published"

# Positional columns: _recipe_row indexes into these by position.
# The 8 migration-0008 columns are appended AFTER updated_at, so the
# two appended select expressions shift from 9/10 to 17/18:
#   0 id, 1 author_id, 2 title, 3 cover_image, 4 cook_time,
#   5 likes_count, 6 status, 7 created_at, 8 updated_at,
#   9 description, 10 source_url, 11 category, 12 language,
#   13 difficulty, 14 taste, 15 slug, 16 author (TEXT),
#   17 ingredient_count, 18 author_name.
_RECIPE_COLS = ("r.id, r.author_id, r.title, r.cover_image,"
                " r.cook_time, r.likes_count, r.status,"
                " r.created_at, r.updated_at,"
                " r.description, r.source_url, r.category, r.language,"
                " r.difficulty, r.taste, r.slug, r.author")


def _author_shape(author_id, author_name):
    if author_id is None:
        return None
    return {"id": str(author_id), "name": author_name}


def _recipe_row(row, liked=None, saved=None) -> dict:
    out = {
        "id": str(row[0]),
        "title": row[2],
        "cover_image": row[3],
        "cook_time": row[4],
        "ingredient_count": row[17],
        "likes_count": row[5],
        "created_at": row[7].isoformat() if row[7] else None,
        "author": _author_shape(row[1], row[18]),
        "description": row[9],
        "source_url": row[10],
        "category": row[11],
        "language": row[12],
        "difficulty": row[13],
        "taste": row[14],
        "slug": row[15],
        "author_name": row[16],
    }
    if liked is not None:
        out["liked"] = liked
    if saved is not None:
        out["saved"] = saved
    return out


def _parse_steps(steps_json) -> list[dict]:
    """steps_json -> [{text, image}]; image only when the author gave one.

    Stored shape is a JSON array of strings or of {text, image}
    objects; anything else degrades to an empty list, never fabricated
    steps.
    """
    if isinstance(steps_json, str):
        try:
            steps_json = json.loads(steps_json)
        except (ValueError, TypeError):
            return []
    if not isinstance(steps_json, list):
        return []
    steps: list[dict] = []
    for item in steps_json:
        if isinstance(item, str):
            steps.append({"text": item, "image": None})
        elif isinstance(item, dict):
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value:
                image = item.get("image")
                steps.append({
                    "text": text_value,
                    "image": image if isinstance(image, str) else None,
                })
    return steps


def _list_where(ingredient: str | None, author_id: uuid.UUID | None,
                language: str | None = None,
                category: str | None = None):
    """Shared WHERE fragments + params for the list query."""
    where = ["r.status = :published"]
    params: dict = {"published": PUBLISHED}
    if ingredient is not None:
        # Canonical match only: recipe_ingredients ->
        # master_ingredients.canonical_name. Lines with no canonical
        # ingredient (canonical_ingredient_id NULL) never match.
        where.append(
            "EXISTS (SELECT 1 FROM recipe_ingredients ri"
            " JOIN master_ingredients mi"
            " ON mi.id = ri.canonical_ingredient_id"
            " WHERE ri.recipe_id = r.id"
            " AND mi.canonical_name = :ingredient)")
        params["ingredient"] = ingredient
    if author_id is not None:
        where.append("r.author_id = :author_id")
        params["author_id"] = author_id
    if language is not None:
        where.append("r.language = :language")
        params["language"] = language
    if category is not None:
        where.append("r.category = :category")
        params["category"] = category
    return " AND ".join(where), params


def _load_published_or_404(conn, recipe_id: uuid.UUID):
    row = conn.execute(
        text(f"SELECT {_RECIPE_COLS},"
             " (SELECT COUNT(*) FROM recipe_ingredients ri"
             " WHERE ri.recipe_id = r.id) AS ingredient_count,"
             " u.name AS author_name"
             " FROM community_recipes r"
             " LEFT JOIN users u ON u.id = r.author_id"
             " WHERE r.id = :rid AND r.status = :published"),
        {"rid": recipe_id, "published": PUBLISHED},
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return row


def _load_published_by_slug_or_404(conn, slug: str):
    """Same published row, looked up by slug instead of id.

    Slugs are unique across the live seed (186 recipes, 186 distinct
    slugs), so a slug match is unambiguous. An unknown slug is a 404,
    never a 422 — the path value is not a UUID, so FastAPI must not
    validate it as one.
    """
    row = conn.execute(
        text(f"SELECT {_RECIPE_COLS},"
             " (SELECT COUNT(*) FROM recipe_ingredients ri"
             " WHERE ri.recipe_id = r.id) AS ingredient_count,"
             " u.name AS author_name"
             " FROM community_recipes r"
             " LEFT JOIN users u ON u.id = r.author_id"
             " WHERE r.slug = :slug AND r.status = :published"),
        {"slug": slug, "published": PUBLISHED},
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return row


@router.get("")
def list_recipes(
    limit: int = Query(20),
    offset: int = Query(0),
    ingredient: str | None = Query(None),
    author: uuid.UUID | None = Query(None),
    language: str | None = Query(None),
    category: str | None = Query(None),
    ident: Identity | None = Depends(optional_auth),
):
    # Query params are validated by hand (not FastAPI Query(ge/le))
    # because the error contract is 400 for a bad value, while
    # FastAPI's automatic validation returns 422 (knowledge.py).
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400,
                            detail="limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=400,
                            detail="offset must be >= 0")
    if ingredient is not None and not ingredient.strip():
        raise HTTPException(status_code=400,
                            detail="ingredient must not be blank")
    if language is not None and not language.strip():
        raise HTTPException(status_code=400,
                            detail="language must not be blank")
    if category is not None and not category.strip():
        raise HTTPException(status_code=400,
                            detail="category must not be blank")
    where, params = _list_where(
        ingredient.strip() if ingredient is not None else None, author,
        language.strip() if language is not None else None,
        category.strip() if category is not None else None)
    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM community_recipes r"
                 f" WHERE {where}"),
            params,
        ).scalar_one()
        rows = conn.execute(
            text(f"SELECT {_RECIPE_COLS},"
                 " (SELECT COUNT(*) FROM recipe_ingredients ri"
                 " WHERE ri.recipe_id = r.id) AS ingredient_count,"
                 " u.name AS author_name"
                 " FROM community_recipes r"
                 " LEFT JOIN users u ON u.id = r.author_id"
                 f" WHERE {where}"
                 " ORDER BY r.created_at DESC, r.id DESC"
                 " LIMIT :limit OFFSET :offset"),
            {**params, "limit": limit, "offset": offset},
        ).all()
        liked_map: dict[str, bool] = {}
        saved_map: dict[str, bool] = {}
        if ident is not None and rows:
            ids = [r[0] for r in rows]
            for table, target in (("recipe_likes", liked_map),
                                  ("saved_recipes", saved_map)):
                hits = conn.execute(
                    text(f"SELECT recipe_id FROM {table}"
                         " WHERE user_id = :uid AND recipe_id = ANY(:ids)"),
                    {"uid": ident.user_id, "ids": ids},
                ).all()
                for (rid,) in hits:
                    target[str(rid)] = True
        items = [
            _recipe_row(
                row,
                liked_map.get(str(row[0]), False)
                if ident is not None else None,
                saved_map.get(str(row[0]), False)
                if ident is not None else None,
            )
            for row in rows
        ]
    return {"items": items, "total": total, "limit": limit,
            "offset": offset}


@router.get("/{recipe_id}")
def get_recipe(recipe_id: str,
               ident: Identity | None = Depends(optional_auth)):
    """Detail by UUID or by slug.

    The path value is a plain str (not uuid.UUID): a slug such as
    ``ga-nuong-co-xa-huong`` must not 422. A value that parses as a
    UUID is looked up by id (unchanged behaviour); anything else is
    looked up by slug. Unknown id and unknown slug are both 404.
    """
    engine = get_engine()
    with engine.connect() as conn:
        try:
            recipe_uuid = uuid.UUID(recipe_id)
        except ValueError:
            row = _load_published_by_slug_or_404(conn, recipe_id)
        else:
            row = _load_published_or_404(conn, recipe_uuid)
        # The resolved id — the sub-queries below always use the row's
        # own id, never the raw path value (a slug is not an id).
        rid = row[0]
        ing_rows = conn.execute(
            text("SELECT COALESCE(mi.canonical_name, ri.raw_name) AS name,"
                 " ri.amount, ri.unit"
                 " FROM recipe_ingredients ri"
                 " LEFT JOIN master_ingredients mi"
                 " ON mi.id = ri.canonical_ingredient_id"
                 " WHERE ri.recipe_id = :rid"
                 " ORDER BY ri.created_at ASC, ri.id ASC"),
            {"rid": rid},
        ).all()
        ingredients = [
            {"name": name,
             "quantity": float(amount) if amount is not None else None,
             "unit": unit}
            for name, amount, unit in ing_rows
        ]
        steps_row = conn.execute(
            text("SELECT steps_json FROM community_recipes"
                 " WHERE id = :rid"),
            {"rid": rid},
        ).first()
        comment_count = conn.execute(
            text("SELECT COUNT(*) FROM recipe_comments"
                 " WHERE recipe_id = :rid"),
            {"rid": rid},
        ).scalar_one()
        saved_count = conn.execute(
            text("SELECT COUNT(*) FROM saved_recipes"
                 " WHERE recipe_id = :rid"),
            {"rid": rid},
        ).scalar_one()
        author_recipe_count = 0
        if row[1] is not None:
            author_recipe_count = conn.execute(
                text("SELECT COUNT(*) FROM community_recipes"
                     " WHERE author_id = :aid AND status = :published"),
                {"aid": row[1], "published": PUBLISHED},
            ).scalar_one()
        liked = saved = None
        if ident is not None:
            liked = conn.execute(
                text("SELECT 1 FROM recipe_likes"
                     " WHERE recipe_id = :rid AND user_id = :uid"),
                {"rid": rid, "uid": ident.user_id},
            ).first() is not None
            saved = conn.execute(
                text("SELECT 1 FROM saved_recipes"
                     " WHERE recipe_id = :rid AND user_id = :uid"),
                {"rid": rid, "uid": ident.user_id},
            ).first() is not None
    out = _recipe_row(row, liked, saved)
    out["ingredients"] = ingredients
    out["steps"] = _parse_steps(steps_row[0] if steps_row else None)
    out["comment_count"] = comment_count
    out["saved_count"] = saved_count
    out["author_recipe_count"] = author_recipe_count
    return out


def _toggle(conn, table: str, recipe_id: uuid.UUID, user_id: uuid.UUID,
            insert: bool) -> bool:
    """Insert-or-delete one like/save row; True iff a row changed."""
    if insert:
        row = conn.execute(
            text(f"INSERT INTO {table} (recipe_id, user_id)"
                 " VALUES (:rid, :uid)"
                 " ON CONFLICT (recipe_id, user_id) DO NOTHING"
                 " RETURNING id"),
            {"rid": recipe_id, "uid": user_id},
        ).first()
        return row is not None
    row = conn.execute(
        text(f"DELETE FROM {table}"
             " WHERE recipe_id = :rid AND user_id = :uid"
             " RETURNING id"),
        {"rid": recipe_id, "uid": user_id},
    ).first()
    return row is not None


def _adjust_likes_count(conn, recipe_id: uuid.UUID, delta: int) -> int:
    """Apply a likes_count delta (delta is +1 or -1, floor 0)."""
    return conn.execute(
        text("UPDATE community_recipes"
             " SET likes_count = GREATEST(likes_count + :delta, 0),"
             " updated_at = now()"
             " WHERE id = :rid RETURNING likes_count"),
        {"delta": delta, "rid": recipe_id},
    ).scalar_one()


def _like_unlike(recipe_id: uuid.UUID, ident: Identity, like: bool):
    engine = get_engine()
    with engine.begin() as conn:
        _load_published_or_404(conn, recipe_id)
        changed = _toggle(conn, "recipe_likes", recipe_id,
                          ident.user_id, like)
        if changed:
            count = _adjust_likes_count(conn, recipe_id, 1 if like else -1)
        else:
            count = conn.execute(
                text("SELECT likes_count FROM community_recipes"
                     " WHERE id = :rid"),
                {"rid": recipe_id},
            ).scalar_one()
    return {"id": str(recipe_id), "likes_count": count, "liked": like}


def _save_unsave(recipe_id: uuid.UUID, ident: Identity, save: bool):
    engine = get_engine()
    with engine.begin() as conn:
        _load_published_or_404(conn, recipe_id)
        _toggle(conn, "saved_recipes", recipe_id, ident.user_id, save)
    return {"id": str(recipe_id), "saved": save}


@router.post("/{recipe_id}/like")
def like_recipe(recipe_id: uuid.UUID,
                ident: Identity = Depends(require_auth)):
    return _like_unlike(recipe_id, ident, True)


@router.post("/{recipe_id}/unlike")
def unlike_recipe(recipe_id: uuid.UUID,
                  ident: Identity = Depends(require_auth)):
    return _like_unlike(recipe_id, ident, False)


@router.post("/{recipe_id}/save")
def save_recipe(recipe_id: uuid.UUID,
                ident: Identity = Depends(require_auth)):
    return _save_unsave(recipe_id, ident, True)


@router.post("/{recipe_id}/unsave")
def unsave_recipe(recipe_id: uuid.UUID,
                  ident: Identity = Depends(require_auth)):
    return _save_unsave(recipe_id, ident, False)
