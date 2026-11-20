"""Shopping-list endpoints (Phase 2 design §3.2, §3.3, §5.1, §5.2, §5.4).

- GET /api/v2/shopping-lists: household-scoped, newest first, each
  list with its "items" array.
- POST /api/v2/shopping-lists: create an open list (409 when the
  household already has one — the partial unique index
  ux_shopping_lists_open raises IntegrityError). With
  ``source_recipe_id`` the missing items are generated from the recipe
  (§3.2); list + items are created in ONE DB transaction.
- POST /api/v2/shopping-lists/from-recipe: same generation, defined
  BEFORE the /{id} routes so "from-recipe" is never read as an id.
- GET / PATCH / DELETE /api/v2/shopping-lists/{id}; item add / patch /
  delete; POST /{id}/complete. open -> done is terminal (§5.2).

Shared generation rule (_generate_items_from_recipe): for each
recipe_ingredient with a canonical_ingredient_id, sum the household's
unconsumed inventory of that ingredient in the recipe unit; skip when
the household already has at least the needed amount, otherwise add
an item for the shortfall (amount null when the recipe amount is
null). Without a canonical id the item is added as-is. No restriction
by recipe status (the design does not impose one).
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

from app.auth import Identity, require_auth, require_household_member_403
from app.db import get_engine

router = APIRouter(prefix="/api/v2/shopping-lists",
                   tags=["shopping-lists"])

LIST_STATUSES = ("open", "done")

_LIST_COLS = ("id, household_id, source_recipe_id, status,"
              " completed_at, created_at, updated_at")
_ITEM_COLS = ("id, shopping_list_id, master_ingredient_id, raw_name,"
              " amount, unit, checked, created_at, updated_at")


def _list_row(row) -> dict:
    return {
        "id": str(row[0]), "household_id": str(row[1]),
        "source_recipe_id": str(row[2]) if row[2] else None,
        "status": row[3],
        "completed_at": row[4].isoformat() if row[4] else None,
        "created_at": row[5].isoformat() if row[5] else None,
        "updated_at": row[6].isoformat() if row[6] else None,
    }


def _item_row(row) -> dict:
    return {
        "id": str(row[0]), "shopping_list_id": str(row[1]),
        "master_ingredient_id": str(row[2]) if row[2] else None,
        "raw_name": row[3],
        "amount": float(row[4]) if row[4] is not None else None,
        "unit": row[5], "checked": row[6],
        "created_at": row[7].isoformat() if row[7] else None,
        "updated_at": row[8].isoformat() if row[8] else None,
    }


def _list_with_items(conn, list_row) -> dict:
    out = _list_row(list_row)
    item_rows = conn.execute(
        text(f"SELECT {_ITEM_COLS} FROM shopping_list_items"
             " WHERE shopping_list_id=:lid"
             " ORDER BY created_at ASC, id ASC"),
        {"lid": list_row[0]},
    ).all()
    out["items"] = [_item_row(r) for r in item_rows]
    return out


def _load_list_or_404(conn, list_id: uuid.UUID):
    row = conn.execute(
        text(f"SELECT {_LIST_COLS} FROM shopping_lists WHERE id=:lid"),
        {"lid": list_id},
    ).first()
    if not row:
        raise HTTPException(status_code=404,
                            detail="Shopping list not found")
    return row


def _load_recipe_or_404(conn, recipe_id: uuid.UUID):
    row = conn.execute(
        text("SELECT id FROM community_recipes WHERE id=:rid"),
        {"rid": recipe_id},
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return row


def _insert_item(conn, list_id: uuid.UUID,
                 master_ingredient_id: uuid.UUID | None,
                 raw_name: str, amount: Decimal | None,
                 unit: str | None) -> dict:
    row = conn.execute(
        text(f"INSERT INTO shopping_list_items (shopping_list_id,"
             " master_ingredient_id, raw_name, amount, unit)"
             " VALUES (:lid, :mid, :raw, :amount, :unit)"
             f" RETURNING {_ITEM_COLS}"),
        {"lid": list_id, "mid": master_ingredient_id,
         "raw": raw_name, "amount": amount, "unit": unit},
    ).first()
    return _item_row(row)


def _generate_items_from_recipe(conn, household_id: uuid.UUID,
                                recipe_id: uuid.UUID,
                                list_id: uuid.UUID) -> list[dict]:
    """Insert the missing items for a recipe; return the shaped items."""
    recipe_rows = conn.execute(
        text("SELECT id, canonical_ingredient_id, raw_name, amount, unit"
             " FROM recipe_ingredients WHERE recipe_id=:rid"
             " ORDER BY created_at ASC, id ASC"),
        {"rid": recipe_id},
    ).all()
    items: list[dict] = []
    for _rid, canonical_id, raw_name, amount, unit in recipe_rows:
        if canonical_id is not None:
            available = conn.execute(
                text("SELECT COALESCE(SUM(quantity), 0)"
                     " FROM inventory_items"
                     " WHERE household_id=:h"
                     " AND canonical_ingredient_id=:cid"
                     " AND status != 'consumed' AND unit=:unit"),
                {"h": household_id, "cid": canonical_id,
                 "unit": unit},
            ).scalar_one()
            if amount is not None and available >= amount:
                continue
            name = raw_name
            if name is None:
                name = conn.execute(
                    text("SELECT canonical_name FROM master_ingredients"
                         " WHERE id=:mid"),
                    {"mid": canonical_id},
                ).scalar_one_or_none()
            if name is None:
                # raw_name is NOT NULL on the item; a recipe line with
                # neither a name nor a canonical ingredient cannot be
                # listed, so it is skipped.
                continue
            need = (amount - available) if amount is not None else None
            items.append(_insert_item(conn, list_id, canonical_id,
                                      name, need, unit))
        else:
            if raw_name is None:
                continue
            items.append(_insert_item(conn, list_id, None, raw_name,
                                      amount, unit))
    return items


def _create_list(conn, household_id: uuid.UUID,
                 source_recipe_id: uuid.UUID | None) -> dict:
    """Insert the list row (+ generated items) and return it shaped."""
    list_row = conn.execute(
        text(f"INSERT INTO shopping_lists (household_id,"
             " source_recipe_id) VALUES (:h, :rid)"
             f" RETURNING {_LIST_COLS}"),
        {"h": household_id, "rid": source_recipe_id},
    ).first()
    out = _list_row(list_row)
    if source_recipe_id is not None:
        out["items"] = _generate_items_from_recipe(
            conn, household_id, source_recipe_id, list_row[0])
    else:
        out["items"] = []
    return out


class ShoppingListCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    household_id: uuid.UUID
    source_recipe_id: uuid.UUID | None = None


class FromRecipeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    household_id: uuid.UUID
    recipe_id: uuid.UUID


class ShoppingListPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = None


class ShoppingListItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_name: str
    amount: Decimal | None = None
    unit: str | None = None
    master_ingredient_id: uuid.UUID | None = None


class ShoppingListItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checked: bool | None = None
    amount: Decimal | None = None
    unit: str | None = None


def _create_list_or_409(body_household_id: uuid.UUID,
                        source_recipe_id: uuid.UUID | None) -> dict:
    """Create a list in one transaction; open-list clash -> 409 (§3.2)."""
    engine = get_engine()
    try:
        with engine.begin() as conn:
            if source_recipe_id is not None:
                _load_recipe_or_404(conn, source_recipe_id)
            return _create_list(conn, body_household_id,
                                source_recipe_id)
    except IntegrityError as exc:
        if "ux_shopping_lists_open" in str(exc.orig):
            raise HTTPException(
                status_code=409,
                detail="Household already has an open shopping list")
        raise


@router.get("")
def list_shopping_lists(household_id: uuid.UUID = Query(...),
                        status: str | None = Query(None),
                        ident: Identity = Depends(require_auth)):
    require_household_member_403(household_id, ident)
    if status is not None and status not in LIST_STATUSES:
        raise HTTPException(
            status_code=400, detail="status must be 'open' or 'done'")
    engine = get_engine()
    with engine.connect() as conn:
        query = (f"SELECT {_LIST_COLS} FROM shopping_lists"
                 " WHERE household_id=:h")
        params: dict = {"h": household_id}
        if status is not None:
            query += " AND status=:status"
            params["status"] = status
        query += " ORDER BY created_at DESC, id DESC"
        list_rows = conn.execute(text(query), params).all()
        out = [_list_row(r) for r in list_rows]
        if list_rows:
            item_rows = conn.execute(
                text(f"SELECT {_ITEM_COLS} FROM shopping_list_items"
                     " WHERE shopping_list_id IN :lids"
                     " ORDER BY created_at ASC, id ASC").bindparams(
                         bindparam("lids", expanding=True)),
                {"lids": [r[0] for r in list_rows]},
            ).all()
            by_list: dict[str, list[dict]] = {}
            for item in item_rows:
                by_list.setdefault(str(item[1]), []).append(
                    _item_row(item))
            for entry in out:
                entry["items"] = by_list.get(entry["id"], [])
        else:
            for entry in out:
                entry["items"] = []
    return out


@router.post("", status_code=201)
def create_shopping_list(body: ShoppingListCreate,
                         ident: Identity = Depends(require_auth)):
    require_household_member_403(body.household_id, ident)
    return _create_list_or_409(body.household_id, body.source_recipe_id)


@router.post("/from-recipe", status_code=201)
def create_shopping_list_from_recipe(
        body: FromRecipeCreate,
        ident: Identity = Depends(require_auth)):
    require_household_member_403(body.household_id, ident)
    return _create_list_or_409(body.household_id, body.recipe_id)


@router.get("/{list_id}")
def get_shopping_list(list_id: uuid.UUID,
                      ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.connect() as conn:
        row = _load_list_or_404(conn, list_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        return _list_with_items(conn, row)


@router.patch("/{list_id}")
def patch_shopping_list(list_id: uuid.UUID,
                        body: ShoppingListPatch,
                        ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.begin() as conn:
        row = _load_list_or_404(conn, list_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        if body.status is None:
            raise HTTPException(status_code=400,
                                detail="Nothing to update")
        if body.status != "done":
            raise HTTPException(
                status_code=400, detail="status must be 'done'")
        if row[3] == "done":
            raise HTTPException(
                status_code=409,
                detail="Shopping list is already done")
        updated = conn.execute(
            text(f"UPDATE shopping_lists SET status='done',"
                 " completed_at=now(), updated_at=now()"
                 " WHERE id=:lid"
                 f" RETURNING {_LIST_COLS}"),
            {"lid": list_id},
        ).first()
        return _list_with_items(conn, updated)


@router.delete("/{list_id}", status_code=204)
def delete_shopping_list(list_id: uuid.UUID,
                         ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.begin() as conn:
        row = _load_list_or_404(conn, list_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        conn.execute(
            text("DELETE FROM shopping_lists WHERE id=:lid"),
            {"lid": list_id},
        )
    return None


@router.post("/{list_id}/items", status_code=201)
def add_shopping_list_item(list_id: uuid.UUID,
                           body: ShoppingListItemCreate,
                           ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.begin() as conn:
        row = _load_list_or_404(conn, list_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        if row[3] == "done":
            raise HTTPException(
                status_code=409,
                detail="Cannot add items to a done shopping list")
        if not body.raw_name.strip():
            raise HTTPException(status_code=400,
                                detail="raw_name is required")
        if body.amount is not None and body.amount <= 0:
            raise HTTPException(status_code=400,
                                detail="amount must be > 0")
        if body.master_ingredient_id is not None:
            exists = conn.execute(
                text("SELECT 1 FROM master_ingredients WHERE id=:mid"),
                {"mid": body.master_ingredient_id},
            ).first()
            if not exists:
                raise HTTPException(
                    status_code=404,
                    detail="Master ingredient not found")
        return _insert_item(conn, list_id, body.master_ingredient_id,
                            body.raw_name, body.amount, body.unit)


@router.patch("/{list_id}/items/{item_id}")
def patch_shopping_list_item(list_id: uuid.UUID,
                             item_id: uuid.UUID,
                             body: ShoppingListItemPatch,
                             ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.begin() as conn:
        list_row = _load_list_or_404(conn, list_id)
        require_household_member_403(uuid.UUID(str(list_row[1])), ident)
        row = conn.execute(
            text(f"SELECT {_ITEM_COLS} FROM shopping_list_items"
                 " WHERE id=:iid AND shopping_list_id=:lid"),
            {"iid": item_id, "lid": list_id},
        ).first()
        if not row:
            raise HTTPException(
                status_code=404, detail="Shopping list item not found")
        if (body.checked is None and body.amount is None
                and body.unit is None):
            raise HTTPException(status_code=400,
                                detail="Nothing to update")
        if body.amount is not None and body.amount <= 0:
            raise HTTPException(status_code=400,
                                detail="amount must be > 0")
        sets: list[str] = []
        params: dict = {"iid": item_id}
        if body.checked is not None:
            sets.append("checked=:checked")
            params["checked"] = body.checked
        if body.amount is not None:
            sets.append("amount=:amount")
            params["amount"] = body.amount
        if body.unit is not None:
            sets.append("unit=:unit")
            params["unit"] = body.unit
        sets.append("updated_at=now()")
        updated = conn.execute(
            text(f"UPDATE shopping_list_items SET {', '.join(sets)}"
                 " WHERE id=:iid"
                 f" RETURNING {_ITEM_COLS}"),
            params,
        ).first()
    return _item_row(updated)


@router.delete("/{list_id}/items/{item_id}", status_code=204)
def delete_shopping_list_item(list_id: uuid.UUID,
                              item_id: uuid.UUID,
                              ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.begin() as conn:
        list_row = _load_list_or_404(conn, list_id)
        require_household_member_403(uuid.UUID(str(list_row[1])), ident)
        row = conn.execute(
            text("SELECT id FROM shopping_list_items"
                 " WHERE id=:iid AND shopping_list_id=:lid"),
            {"iid": item_id, "lid": list_id},
        ).first()
        if not row:
            raise HTTPException(
                status_code=404, detail="Shopping list item not found")
        conn.execute(
            text("DELETE FROM shopping_list_items WHERE id=:iid"),
            {"iid": item_id},
        )
    return None


@router.post("/{list_id}/complete")
def complete_shopping_list(list_id: uuid.UUID,
                           ident: Identity = Depends(require_auth)):
    engine = get_engine()
    with engine.begin() as conn:
        row = _load_list_or_404(conn, list_id)
        require_household_member_403(uuid.UUID(str(row[1])), ident)
        if row[3] == "done":
            raise HTTPException(
                status_code=409,
                detail="Shopping list is already done")
        updated = conn.execute(
            text(f"UPDATE shopping_lists SET status='done',"
                 " completed_at=now(), updated_at=now()"
                 " WHERE id=:lid"
                 f" RETURNING {_LIST_COLS}"),
            {"lid": list_id},
        ).first()
        return _list_with_items(conn, updated)
