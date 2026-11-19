"""Deterministic stand-in for Qwen 14B receipt parsing, for eval runs
that must not depend on the GPU (design §7 fallback idea, harness-only).

``mock_parse_receipt_text`` has the same signature as
``app.qwen.parse_receipt_text`` and parses OCR text line by line with
a regex — it NEVER sees ground truth, only the OCR text the real Qwen
would receive. It understands the canned mock-OCR text
(``app.ocr.MOCK_OCR_TEXT``) and any receipt text in the same
``<name> <qty><unit> <price>`` / ``合计 <total>`` shape.

Canonical-name suggestions come from a small substring map keyed on
the printed name, and only a name that is in the ``canonical_names``
list the worker passes in is ever suggested — exactly the
"Qwen suggests, worker resolves" split of design §6.2 steps 3-4.
This is a test double: it measures the harness + the mapping /
reconciliation pipeline, NOT Qwen's real accuracy. The real > 90%
gate needs the real Qwen path (or Baidu OCR) on real receipts.
"""
from __future__ import annotations

import re
from datetime import datetime

from app.qwen import QwenParseError

_LINE_RE = re.compile(
    r"^(.+?)\s+(-?\d+(?:\.\d+)?)\s*([^\d\s]+)\s+(-?\d+(?:\.\d+)?)\s*$")
_TOTAL_RE = re.compile(r"合计\s*(-?\d+(?:\.\d+)?)")
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)")

# Printed-name substring -> canonical ingredient name (seed list §4).
# Only used when the canonical name is in the worker-supplied list.
_CANONICAL_HINTS = {
    "农夫山泉": "Nước suối",
    "鸡蛋": "Trứng gà",
    "大米": "Gạo",
    "青菜": "Rau cải",
    "纯牛奶": "Sữa tươi",
    "西红柿": "Cà chua",
    "五花肉": "Thịt ba chỉ",
    "豆腐": "Đậu phụ",
    "食盐": "Muối",
}

_DISCOUNT_HINTS = ("优惠", "抵扣", "折扣", "袋费", "服务费", "税")


def _suggest_canonical(raw_name: str,
                       canonical_names: list[str] | None) -> str | None:
    if not canonical_names:
        return None
    for fragment, canonical in _CANONICAL_HINTS.items():
        if fragment in raw_name and canonical in canonical_names:
            return canonical
    return None


def mock_parse_receipt_text(ocr_text: str,
                            canonical_names: list[str] | None = None,
                            timeout: float | None = None) -> dict:
    """Parse OCR text into the §6.3 JSON contract, deterministically."""
    store_name = None
    purchased_at = None
    total_amount = None
    lines: list[dict] = []
    for raw in (ocr_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        total_m = _TOTAL_RE.search(line)
        if total_m:
            total_amount = float(total_m.group(1))
            continue
        date_m = _DATE_RE.search(line)
        if date_m and purchased_at is None:
            try:
                purchased_at = datetime.fromisoformat(
                    date_m.group(1)).isoformat() + "+08:00"
            except ValueError:
                purchased_at = None
            continue
        m = _LINE_RE.match(line)
        if m:
            raw_name, qty, unit, price = (m.group(1).strip(),
                                          float(m.group(2)), m.group(3),
                                          float(m.group(4)))
            is_stock = price >= 0 and not any(
                h in raw_name for h in _DISCOUNT_HINTS)
            lines.append({
                "raw_name": raw_name, "quantity": qty, "unit": unit,
                "price": price,
                "canonical_name": _suggest_canonical(raw_name,
                                                     canonical_names),
                "is_stock_item": is_stock,
            })
            continue
        if store_name is None:
            store_name = line
    if not lines:
        raise QwenParseError(
            "mock Qwen parser: no receipt lines found in OCR text")
    return {
        "store_name": store_name,
        "purchased_at": purchased_at,
        "total_amount": total_amount,
        "currency": "CNY",
        "lines": lines,
    }
