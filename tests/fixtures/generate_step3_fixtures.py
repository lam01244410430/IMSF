"""Generate the FIVE Step 3 synthetic receipt fixtures (design §8 gate).

Each receipt is rendered as a PNG with PIL (WenQuanYi Zen Hei CJK
font) and labelled SYNTHETIC, plus a matching ground-truth JSON.
All totals are exact sums of their lines except (e), which is the
deliberate mismatch case.

- (a) step3_a_yonghui: 永辉超市, 4 lines, total = exact sum 56.10.
- (b) step3_b_hema: 盒马鲜生, 3 lines incl. a discount line (negative
  price, is_stock_item=false), total = exact sum 19.40.
- (c) step3_c_unmatched: one line (可口可乐 330ml) whose brand is NOT
  in master_ingredients -> canonical_ingredient_id must stay NULL,
  total = exact sum 48.80.
- (d) step3_d_carrefour: 家乐福, 5 lines, total = exact sum 47.80.
- (e) step3_e_mismatch: lines sum 95.00, printed total 100.00
  (5.00% off) -> must end up needs_review per §6.4.

Run on Oregon: python tests/fixtures/generate_step3_fixtures.py
Writes: tests/fixtures/step3_*.png + step3_*.json
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

FIXTURES = {
    "step3_a_yonghui": {
        "store": "永辉超市",
        "date": "2026-11-20 09:12",
        "render_lines": [
            "农夫山泉 550ml   2瓶   4.00",
            "鸡蛋   1盒   12.80",
            "大米 5kg   1袋   32.50",
            "青菜   1斤   6.80",
        ],
        "total_render": "合计   56.10",
        "ground_truth": {
            "store_name": "永辉超市",
            "purchased_at": "2026-11-20T09:12:00+08:00",
            "total_amount": 56.10,
            "currency": "CNY",
            "lines": [
                {"raw_name": "农夫山泉 550ml", "quantity": 2, "unit": "瓶",
                 "price": 4.00, "canonical_name": "Nước suối",
                 "is_stock_item": True},
                {"raw_name": "鸡蛋", "quantity": 1, "unit": "盒",
                 "price": 12.80, "canonical_name": "Trứng gà",
                 "is_stock_item": True},
                {"raw_name": "大米 5kg", "quantity": 1, "unit": "袋",
                 "price": 32.50, "canonical_name": "Gạo",
                 "is_stock_item": True},
                {"raw_name": "青菜", "quantity": 1, "unit": "斤",
                 "price": 6.80, "canonical_name": "Rau cải",
                 "is_stock_item": True},
            ],
        },
    },
    "step3_b_hema": {
        "store": "盒马鲜生",
        "date": "2026-11-20 10:05",
        "render_lines": [
            "纯牛奶   1盒   15.90",
            "西红柿   1斤   8.50",
            "优惠券抵扣   1份   -5.00",
        ],
        "total_render": "合计   19.40",
        "ground_truth": {
            "store_name": "盒马鲜生",
            "purchased_at": "2026-11-20T10:05:00+08:00",
            "total_amount": 19.40,
            "currency": "CNY",
            "lines": [
                {"raw_name": "纯牛奶", "quantity": 1, "unit": "盒",
                 "price": 15.90, "canonical_name": "Sữa tươi",
                 "is_stock_item": True},
                {"raw_name": "西红柿", "quantity": 1, "unit": "斤",
                 "price": 8.50, "canonical_name": "Cà chua",
                 "is_stock_item": True},
                {"raw_name": "优惠券抵扣", "quantity": 1, "unit": "份",
                 "price": -5.00, "canonical_name": None,
                 "is_stock_item": False},
            ],
        },
    },
    "step3_c_unmatched": {
        "store": "永辉超市",
        "date": "2026-11-20 11:30",
        "render_lines": [
            "可口可乐 330ml   1罐   3.50",
            "鸡蛋   1盒   12.80",
            "大米 5kg   1袋   32.50",
        ],
        "total_render": "合计   48.80",
        "ground_truth": {
            "store_name": "永辉超市",
            "purchased_at": "2026-11-20T11:30:00+08:00",
            "total_amount": 48.80,
            "currency": "CNY",
            "lines": [
                {"raw_name": "可口可乐 330ml", "quantity": 1, "unit": "罐",
                 "price": 3.50, "canonical_name": None,
                 "is_stock_item": True},
                {"raw_name": "鸡蛋", "quantity": 1, "unit": "盒",
                 "price": 12.80, "canonical_name": "Trứng gà",
                 "is_stock_item": True},
                {"raw_name": "大米 5kg", "quantity": 1, "unit": "袋",
                 "price": 32.50, "canonical_name": "Gạo",
                 "is_stock_item": True},
            ],
        },
    },
    "step3_d_carrefour": {
        "store": "家乐福",
        "date": "2026-11-20 14:20",
        "render_lines": [
            "农夫山泉 550ml   2瓶   4.00",
            "鸡蛋   1盒   12.80",
            "五花肉   1斤   25.00",
            "豆腐   1块   3.50",
            "食盐   1袋   2.50",
        ],
        "total_render": "合计   47.80",
        "ground_truth": {
            "store_name": "家乐福",
            "purchased_at": "2026-11-20T14:20:00+08:00",
            "total_amount": 47.80,
            "currency": "CNY",
            "lines": [
                {"raw_name": "农夫山泉 550ml", "quantity": 2, "unit": "瓶",
                 "price": 4.00, "canonical_name": "Nước suối",
                 "is_stock_item": True},
                {"raw_name": "鸡蛋", "quantity": 1, "unit": "盒",
                 "price": 12.80, "canonical_name": "Trứng gà",
                 "is_stock_item": True},
                {"raw_name": "五花肉", "quantity": 1, "unit": "斤",
                 "price": 25.00, "canonical_name": "Thịt ba chỉ",
                 "is_stock_item": True},
                {"raw_name": "豆腐", "quantity": 1, "unit": "块",
                 "price": 3.50, "canonical_name": "Đậu phụ",
                 "is_stock_item": True},
                {"raw_name": "食盐", "quantity": 1, "unit": "袋",
                 "price": 2.50, "canonical_name": "Muối",
                 "is_stock_item": True},
            ],
        },
    },
    "step3_e_mismatch": {
        "store": "永辉超市",
        "date": "2026-11-20 16:40",
        "render_lines": [
            "大米 5kg   1袋   32.50",
            "五花肉   1斤   25.00",
            "纯牛奶   1盒   15.90",
            "鸡蛋   1盒   12.80",
            "食盐   1袋   8.80",
        ],
        # Deliberate mismatch: lines sum 95.00, printed total 100.00
        # (diff 5.00 / 100.00 = 5.00% > 2% -> needs_review per §6.4).
        "total_render": "合计   100.00",
        "ground_truth": {
            "store_name": "永辉超市",
            "purchased_at": "2026-11-20T16:40:00+08:00",
            "total_amount": 100.00,
            "currency": "CNY",
            "lines": [
                {"raw_name": "大米 5kg", "quantity": 1, "unit": "袋",
                 "price": 32.50, "canonical_name": "Gạo",
                 "is_stock_item": True},
                {"raw_name": "五花肉", "quantity": 1, "unit": "斤",
                 "price": 25.00, "canonical_name": "Thịt ba chỉ",
                 "is_stock_item": True},
                {"raw_name": "纯牛奶", "quantity": 1, "unit": "盒",
                 "price": 15.90, "canonical_name": "Sữa tươi",
                 "is_stock_item": True},
                {"raw_name": "鸡蛋", "quantity": 1, "unit": "盒",
                 "price": 12.80, "canonical_name": "Trứng gà",
                 "is_stock_item": True},
                {"raw_name": "食盐", "quantity": 1, "unit": "袋",
                 "price": 8.80, "canonical_name": "Muối",
                 "is_stock_item": True},
            ],
        },
    },
}


def render(name, spec) -> None:
    rows = [(spec["store"], 44), (spec["date"], 28), ("", 20)]
    rows += [(t, 30) for t in spec["render_lines"]]
    rows += [("", 20), (spec["total_render"], 34), ("", 20),
             ("SYNTHETIC TEST RECEIPT - NOT REAL", 22)]
    height = 40 + sum(size + 14 for _, size in rows) + 40
    img = Image.new("RGB", (640, height), "white")
    draw = ImageDraw.Draw(img)
    y = 40
    for text, size in rows:
        font = ImageFont.truetype(FONT_PATH, size)
        draw.text((40, y), text, fill="black", font=font)
        y += size + 14
    draw.rectangle([15, 15, 625, height - 15], outline="black", width=2)
    out_png = HERE / f"{name}.png"
    img.save(out_png, "PNG")
    (HERE / f"{name}.json").write_text(
        json.dumps(spec["ground_truth"], ensure_ascii=False, indent=2),
        encoding="utf-8")
    # Sanity: ground-truth lines sum (except the deliberate mismatch).
    s = sum(ln["price"] for ln in spec["ground_truth"]["lines"])
    print(f"wrote {out_png.name} ({out_png.stat().st_size} bytes)"
          f" lines_sum={s:.2f} total={spec['ground_truth']['total_amount']:.2f}")


def main() -> None:
    for name, spec in FIXTURES.items():
        render(name, spec)


if __name__ == "__main__":
    main()
