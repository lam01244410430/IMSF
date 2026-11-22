"""0010_cn_canonical_seed - seed Chinese canonical ingredients + aliases,
backfill canonical_ingredient_id on the Chinese recipe_ingredients rows.

Why: the 186-recipe import (0008, main @ a833acd) left all 1,023 Chinese
ingredient lines with canonical_ingredient_id NULL, so ?ingredient= only
matched the 20 Vietnamese canonicals and the 100 Chinese recipes were
invisible to ingredient search. This migration seeds the Chinese
canonicals + aliases and backfills the existing rows (no re-import).

Number: 0010, NOT 0009. 0009 was Phase C's admin migration
(0009_admin.py, down_revision 0008, on branch
task/DASH-C-admin-dashboard when this was written). This revision has
down_revision 0008; Phase C's admin migration is now 0011_admin.py
with down_revision 0010, so the chain is 0008 -> 0010 -> 0011 with
a single head and no merge revision is needed.

Seed list re-derived from the LIVE DB's actual raw_name values
(2026-11-22, 289 distinct CN raw_names, 1,023 lines), NOT the
JSON-based counts in ~/workspace/imsf-recipes/cn-canonical-seed-2026-11-22.md
(those were approximate: e.g. 盐 52 live vs 50 JSON, 姜 49 live vs 45,
葱 48 live vs 40, 醋 group 15 live vs 12). Live coverage of this seed,
measured with the repo's own resolve_canonical against the live DB:
574/1,023 lines (56.1%), 94/100 Chinese recipes findable by >=1
ingredient. The 6 unfindable recipes are the five 四物汤 medicinal-herb
soups (their ingredients are all one-offs: 熟地, 当归, 川芎, 白芍, 阿胶,
枸杞) plus 虾仁罗勒意大利面.

Deviations from the plan's 20 groups:
- 21st canonical 五花肉 (10 lines): the plan's verification requires
  ?ingredient=五花肉 to return Chinese recipes, and ?ingredient= matches
  canonical_name exactly, so 五花肉 must BE a canonical (it cannot be
  an alias of the Vietnamese Thịt ba chỉ -- the API would not match it).
- 11 extra variant aliases, all observed in the live raw_names and
  unambiguously the same ingredient in a different form: 姜片->姜,
  蒜瓣->蒜, 植物油/橄榄油/香油/麻油->油, 食盐->盐,
  鲜酱油/黄豆酱油->酱油, 香醋->醋, 水淀粉->淀粉 (+30 lines).
  NOT added: 黄酒 (13 lines, the largest unmatched item -- a distinct
  cooking wine, not a form of 料酒; left for a follow-up decision),
  红糖 (brown sugar -- distinct from 白糖), and the medicinal herbs /
  one-offs (香叶, 胡萝卜, 红枣, 蚝油, 桂皮, ...).
- 3 plan aliases have ZERO live lines (菜籽油, 开水, 温水) and are
  seeded anyway as forward-looking aliases for future imports.
- 盐/水/油 appear in nearly every recipe, so they are weak search
  filters; the real win is the discriminating ones (排骨, 五花肉, 姜).

Shelf lives mirror the Vietnamese analogues seeded by 0002 (same
convention, not invented values): 盐~Muối 365, 姜~Gừng 14, 蒜~Tỏi 60,
生抽/老抽/酱油~Nước tương 180, 油~Dầu ăn 365, 白糖/冰糖~Đường 365,
水~Nước suối 365, 排骨/五花肉~Thịt ba chỉ 3, 淀粉~Gạo/Mì 180.
Dried spices (八角, 胡椒粉, 干辣椒, 花椒) and shelf-stable seasonings
(料酒, 鸡精, 醋) take 365 like the other pantry condiments. 葱 (green
onion) is a perishable vegetable: fridge, 7 days (Rau cải 4 / Cà chua 5
are the perishable-veg analogues; 7 is the scallion value).

Backfill: for every recipe_ingredients row whose recipe has
language='zh' and whose canonical_ingredient_id IS NULL, resolve the
raw_name with the same order as app.reconcile.resolve_canonical
(exact normalised canonical, then longest normalised alias that is a
prefix of the normalised raw_name) and set the id. The resolution is
implemented inline here -- data migrations must not import app code
that may drift -- and tests/test_p308_cn_canonical_seed.py
cross-checks the backfill against resolve_canonical. The UPDATE only
touches NULL rows, and the seed inserts use ON CONFLICT DO NOTHING, so
re-running the migration is a no-op.

No serving column is added (CN serving is blank 100/100; VN serving
is plating prose, not a portion count -- see the plan doc).

Revision ID: 0010
Revises: 0008
Create Date: 2026-11-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0010"
down_revision = "0008"
branch_labels = None
depends_on = None

# (canonical_name, category, default_storage_zone,
#  default_shelf_life_days, [aliases])
SEEDS = [
    ("盐", "gia vị", "pantry", 365, ["食盐"]),
    ("料酒", "gia vị", "pantry", 365, []),
    ("姜", "gia vị", "fridge", 14, ["生姜", "姜片"]),
    ("葱", "rau", "fridge", 7, ["大葱", "香葱", "小葱", "葱花", "葱段"]),
    ("生抽", "gia vị", "pantry", 180, []),
    ("蒜", "gia vị", "pantry", 60, ["大蒜", "蒜瓣"]),
    ("油", "gia vị", "pantry", 365,
     ["食用油", "花生油", "菜籽油", "植物油", "橄榄油", "香油", "麻油"]),
    ("冰糖", "gia vị", "pantry", 365, []),
    ("白糖", "gia vị", "pantry", 365, ["糖"]),
    ("八角", "gia vị", "pantry", 365, ["大料"]),
    ("酱油", "gia vị", "pantry", 180, ["鲜酱油", "黄豆酱油"]),
    ("淀粉", "đồ khô", "pantry", 180,
     ["生粉", "玉米淀粉", "红薯淀粉", "水淀粉"]),
    ("胡椒粉", "gia vị", "pantry", 365, ["白胡椒粉", "黑胡椒粉"]),
    ("干辣椒", "gia vị", "pantry", 365, ["干红辣椒", "红辣椒", "辣椒"]),
    ("老抽", "gia vị", "pantry", 180, []),
    ("花椒", "gia vị", "pantry", 365, []),
    ("水", "đồ uống", "pantry", 365, ["清水", "开水", "温水", "热水"]),
    ("排骨", "thịt", "fridge", 3, []),
    ("鸡精", "gia vị", "pantry", 365, ["味精"]),
    ("醋", "gia vị", "pantry", 365, ["白醋", "陈醋", "米醋", "香醋"]),
    ("五花肉", "thịt", "fridge", 3, []),
]

ALIASES = [(alias, name) for name, _, _, _, aliases in SEEDS
           for alias in aliases]


def _norm(name) -> str:
    """Same normalisation as app.reconcile.normalize_name: strip all
    whitespace, lowercase."""
    return "".join(str(name or "").split()).lower()


def _resolve(raw_name, master_map, alias_map):
    """Same order as app.reconcile.resolve_canonical (exact canonical,
    then longest alias that is a prefix of the raw name). No Qwen
    suggestion here -- the backfill must never invent a canonical.
    Returns the master_ingredients id or None."""
    entry = master_map.get(_norm(raw_name))
    if entry is not None:
        return entry
    norm = _norm(raw_name)
    best = None
    for alias, ingredient_id in alias_map.items():
        if norm.startswith(alias) and (
                best is None or len(alias) > len(best[0])):
            best = (alias, ingredient_id)
    return best[1] if best else None


def upgrade() -> None:
    conn = op.get_bind()
    # --- seed the 21 canonical ingredients (idempotent) ---------------
    conn.execute(
        text(
            "INSERT INTO master_ingredients (canonical_name, category,"
            " default_storage_zone, default_shelf_life_days)"
            " VALUES (:name, :category, :zone, :days)"
            " ON CONFLICT (canonical_name) DO NOTHING"
        ),
        [
            {"name": name, "category": category, "zone": zone,
             "days": days}
            for name, category, zone, days, _ in SEEDS
        ],
    )
    rows = conn.execute(
        text("SELECT id, canonical_name FROM master_ingredients")
    ).fetchall()
    by_name = {row.canonical_name: row.id for row in rows}
    missing = sorted({name for name, _, _, _, _ in SEEDS} - set(by_name))
    if missing:
        raise RuntimeError(
            "0010 seed: canonical ingredient(s) missing after insert: %s"
            % ", ".join(missing)
        )
    # --- seed the 39 aliases (idempotent) ------------------------------
    conn.execute(
        text(
            "INSERT INTO master_ingredient_aliases"
            " (master_ingredient_id, alias)"
            " VALUES (:ingredient_id, :alias)"
            " ON CONFLICT (master_ingredient_id, alias) DO NOTHING"
        ),
        [
            {"ingredient_id": by_name[name], "alias": alias}
            for alias, name in ALIASES
        ],
    )
    # --- backfill the Chinese recipe_ingredients rows ------------------
    master_map = {_norm(name): by_name[name]
                  for name in by_name}
    alias_rows = conn.execute(
        text("SELECT alias, master_ingredient_id"
             " FROM master_ingredient_aliases")
    ).fetchall()
    alias_map = {_norm(row.alias): row.master_ingredient_id
                 for row in alias_rows}
    cn_rows = conn.execute(
        text(
            "SELECT ri.id, ri.raw_name FROM recipe_ingredients ri"
            " JOIN community_recipes r ON r.id = ri.recipe_id"
            " WHERE r.language = 'zh'"
            " AND ri.canonical_ingredient_id IS NULL"
        )
    ).fetchall()
    updates = []
    for row_id, raw_name in cn_rows:
        ingredient_id = _resolve(raw_name, master_map, alias_map)
        if ingredient_id is not None:
            updates.append({"id": row_id, "canon": ingredient_id})
    if updates:
        conn.execute(
            text(
                "UPDATE recipe_ingredients"
                " SET canonical_ingredient_id = :canon"
                " WHERE id = :id AND canonical_ingredient_id IS NULL"
            ),
            updates,
        )
    print(f"0010 backfill: {len(updates)}/{len(cn_rows)} Chinese "
          f"ingredient rows assigned a canonical ingredient")


def downgrade() -> None:
    conn = op.get_bind()
    # FKs are ON DELETE SET NULL (recipe_ingredients, receipt_lines,
    # inventory_items) and ON DELETE CASCADE (aliases), so deleting the
    # ingredients restores the backfilled rows to NULL and removes the
    # aliases. Delete the aliases explicitly first for clarity.
    conn.execute(
        text(
            "DELETE FROM master_ingredient_aliases"
            " WHERE alias IN :aliases"
        ).bindparams(sa.bindparam("aliases", expanding=True)),
        {"aliases": [alias for alias, _ in ALIASES]},
    )
    conn.execute(
        text(
            "DELETE FROM master_ingredients"
            " WHERE canonical_name IN :names"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"names": [name for name, _, _, _, _ in SEEDS]},
    )
