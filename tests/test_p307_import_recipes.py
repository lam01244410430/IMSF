"""P3-07 recipe import: splitter + cook-time map + row builder.

Pure-function tests only -- no database. The live behaviour (counts,
canonical match rate, API filters) is verified by the scratch-DB
import run, not here.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.import_recipes import (  # noqa: E402
    build_recipe_row,
    parse_cook_time,
    split_ingredient,
    _main_group_map,
)


@pytest.mark.parametrize("line,expected", [
    # Basic Arabic amount+unit, both scripts.
    ("五花肉500克", ("五花肉", Decimal("500.00"), "克")),
    ("Thịt ba chỉ 500g", ("Thịt ba chỉ", Decimal("500.00"), "g")),
    ("Đùi dê: 1 cái", ("Đùi dê", Decimal("1.00"), "cái")),
    ("Sả băm: 1M (Lấy phần lõi non)", ("Sả băm", Decimal("1.00"), "M")),
    ("Hành tây: 1/2 củ", ("Hành tây", Decimal("0.50"), "củ")),
    ("Nước dùng gà 1,5l", ("Nước dùng gà", Decimal("1.50"), "l")),
    ("红彩椒1/3个", ("红彩椒", Decimal("0.33"), "个")),
    ("盐1/4小匙", ("盐", Decimal("0.25"), "小匙")),
    # Decimal comma + parenthetical note stripped.
    ("Đường: 2.5g (1M)", ("Đường", Decimal("2.50"), "g")),
    # Multi-word trailing note after the unit is dropped; unit is the
    # single token after the number.
    ("Nước cốt dừa: 1 chén nhỏ", ("Nước cốt dừa", Decimal("1.00"), "chén")),
    ("Cà tím 2 trái vừa", ("Cà tím", Decimal("2.00"), "trái")),
    # First KNOWN-unit candidate wins, not the first number.
    ("Bánh tráng 3 màu 200g", ("Bánh tráng 3 màu", Decimal("200.00"), "g")),
    ("Cải bó xôi 150g Rửa sạch, cắt khúc 5cm",
     ("Cải bó xôi", Decimal("150.00"), "g")),
    # Per-unit specs are skipped on both sides.
    ("Tôm sú 50 con/kg 400g", ("Tôm sú 50 con/kg", Decimal("400.00"), "g")),
    ("Tôm sú size 50 con/1kg 200g",
     ("Tôm sú size 50 con/1kg", Decimal("200.00"), "g")),
    # Empty raw_name guard: the leading "1 con" is skipped.
    ("1 con cá điêu hồng đã làm sạch 600g",
     ("1 con cá điêu hồng đã làm sạch", Decimal("600.00"), "g")),
    # Ranges take the lower bound.
    ("老抽30-40g", ("老抽", Decimal("30.00"), "g")),
    ("冰糖30~40g", ("冰糖", Decimal("30.00"), "g")),
    ("生姜5-6片", ("生姜", Decimal("5.00"), "片")),
    # Trailing bare number: amount, unit "" (never invented).
    ("红枣500", ("红枣", Decimal("500.00"), "")),
    # Chinese-numeral amounts.
    ("料酒一勺", ("料酒", Decimal("1"), "勺")),
    ("贝贝南瓜半个", ("贝贝南瓜", Decimal("0.5"), "个")),
    ("小米辣四个", ("小米辣", Decimal("4"), "个")),
    # Quantity words with no number: NULL / "".
    ("葱适量", ("葱", None, "")),
    ("鸡精少许", ("鸡精", None, "")),
    ("香叶几片", ("香叶", None, "")),
    ("鸡精可选", ("鸡精", None, "")),
    # Composite colon line: whole line is the raw_name, NULL / "".
    ("Gia vị: Dầu điều 2M, muối, tiêu, đường, rượu trắng 30ml",
     ("Gia vị: Dầu điều 2M, muối, tiêu, đường, rượu trắng 30ml", None, "")),
    ("ĂN KÈM: Đồ chua, kim chi", ("ĂN KÈM: Đồ chua, kim chi", None, "")),
    # Bare names and comma lists: NULL / "".
    ("Bột ngọt AJI-NO-MOTO®", ("Bột ngọt AJI-NO-MOTO®", None, "")),
    ("Muối, tiêu, ngò tây, bơ lạt, bột mì",
     ("Muối, tiêu, ngò tây, bơ lạt, bột mì", None, "")),
])
def test_split_ingredient(line, expected):
    raw_name, amount, unit, _notes = split_ingredient(line)
    assert (raw_name, amount, unit) == expected


@pytest.mark.parametrize("value,expected", [
    ("半小时", 30),
    ("廿分钟", 20),
    ("一小时", 60),
    ("十分钟", 10),
    ("三刻钟", 45),
    ("数小时", None),
    ("一天", None),
    ("数天", None),
    ("", None),
    (None, None),
    ("两小时", None),  # unseen string: NULL, never a guessed number.
])
def test_parse_cook_time(value, expected):
    assert parse_cook_time(value) == expected


def test_build_recipe_row_vietnamese():
    recipe = {
        "name": "Đùi dê quay", "slug": "dui-de-quay",
        "source_url": "https://monngonmoingay.com/dui-de-quay/",
        "category": "quay", "description": "  Thịt nướng.  ",
        "image_url": "https://example.com/x.jpg",
        "prep_steps": ["Ướp 2h."], "cook_steps": ["Nướng 45'."],
    }
    row = build_recipe_row(recipe, "vi")
    assert row["title"] == "Đùi dê quay"
    assert row["language"] == "vi"
    assert row["description"] == "Thịt nướng."
    assert json.loads(row["steps_json"]) == ["Ướp 2h.", "Nướng 45'."]
    assert row["cook_time"] is None
    assert row["difficulty"] is None
    assert row["taste"] is None
    assert row["author"] is None


def test_build_recipe_row_chinese():
    recipe = {
        "name": "一品红烧肉", "slug": "recipe-561308",
        "source_url": "https://m.meishichina.com/recipe/561308/",
        "category": "红烧肉", "description": "",
        "image_url": "https://example.com/y.jpg",
        "prep_steps": ["should be ignored"],
        "cook_steps": ["炖60分钟。"],
        "difficulty": "初级", "taste": "咸甜",
        "cook_time": "数小时", "author": "糖芯厨房",
    }
    row = build_recipe_row(recipe, "zh")
    assert row["language"] == "zh"
    assert row["description"] is None  # empty description -> NULL
    assert json.loads(row["steps_json"]) == ["炖60分钟。"]
    assert row["cook_time"] is None  # 数小时 has no number: NULL
    assert row["difficulty"] == "初级"
    assert row["taste"] == "咸甜"
    assert row["author"] == "糖芯厨房"


def test_main_group_map_only_main_group_is_main():
    recipe = {
        "ingredients": ["五花肉500克", "冰糖50克", "葱适量"],
        "ingredient_groups": {
            "主料": ["五花肉500克"],
            "调料": ["冰糖50克", "葱适量"],
        },
    }
    assert _main_group_map(recipe) == [True, False, False]
    assert _main_group_map({"ingredients": ["a", "b"]}) == [False, False]
