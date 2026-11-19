"""Generate the ONE synthetic receipt fixture for Step 2 gates.

Renders a fake supermarket receipt with PIL (WenQuanYi Zen Hei CJK
font). The receipt is clearly labelled SYNTHETIC — it is the Step 2
gate fixture only; the 50 real receipts are Lam's step (Step 4).
Total = exact sum of lines: 4.00 + 12.80 + 32.50 + 6.80 = 56.10.

Run: python tests/fixtures/generate_synthetic_receipt.py
Writes: tests/fixtures/synthetic_receipt.png + synthetic_receipt.json
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

LINES = [
    ("永辉超市", 44),
    ("2026-11-20 09:12", 28),
    ("", 20),
    ("农夫山泉 550ml   2瓶   4.00", 30),
    ("鸡蛋   1盒   12.80", 30),
    ("大米 5kg   1袋   32.50", 30),
    ("青菜   1斤   6.80", 30),
    ("", 20),
    ("合计   56.10", 34),
    ("", 20),
    ("SYNTHETIC TEST RECEIPT - NOT REAL", 22),
]

GROUND_TRUTH = {
    "store_name": "永辉超市",
    "purchased_at": "2026-11-20T09:12:00+08:00",
    "total_amount": 56.10,
    "currency": "CNY",
    "lines": [
        {"raw_name": "农夫山泉 550ml", "quantity": 2, "unit": "瓶",
         "price": 4.00, "canonical_name": "Nước suối", "is_stock_item": True},
        {"raw_name": "鸡蛋", "quantity": 1, "unit": "盒",
         "price": 12.80, "canonical_name": "Trứng gà", "is_stock_item": True},
        {"raw_name": "大米 5kg", "quantity": 1, "unit": "袋",
         "price": 32.50, "canonical_name": "Gạo", "is_stock_item": True},
        {"raw_name": "青菜", "quantity": 1, "unit": "斤",
         "price": 6.80, "canonical_name": "Rau cải", "is_stock_item": True},
    ],
}


def main() -> None:
    img = Image.new("RGB", (640, 760), "white")
    draw = ImageDraw.Draw(img)
    y = 40
    for text, size in LINES:
        font = ImageFont.truetype(FONT_PATH, size)
        draw.text((40, y), text, fill="black", font=font)
        y += size + 14
    # dashed border to look like a receipt
    draw.rectangle([15, 15, 625, 745], outline="black", width=2)
    out_png = HERE / "synthetic_receipt.png"
    img.save(out_png, "PNG")
    (HERE / "synthetic_receipt.json").write_text(
        json.dumps(GROUND_TRUTH, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"wrote {out_png} ({out_png.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
