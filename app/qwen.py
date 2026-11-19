"""Qwen 2.5 14B receipt parsing via Ollama (design §6.2 step 3, §6.3).

Input: OCR raw text. Output: the JSON contract from §6.3
(store_name, purchased_at, total_amount, currency, lines[] with
raw_name / quantity / unit / price / canonical_name / is_stock_item).
If the model returns invalid JSON, the caller retries the parse once
(see worker.main); a second failure raises QwenParseError.
"""

import json
import os

import httpx

QWEN_MODEL = "qwen2.5:14b"


class QwenParseError(RuntimeError):
    """Model output was not valid JSON matching the §6.3 contract."""


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def build_prompt(ocr_text: str, canonical_names: list[str] | None = None) -> str:
    names = ""
    if canonical_names:
        names = (
            "\nKnown canonical ingredient names (use one of these for "
            "canonical_name when the item matches, else null): "
            + ", ".join(canonical_names) + "."
        )
    return (
        "You extract structured data from a Chinese shopping receipt.\n"
        "OCR text of the receipt:\n"
        "```\n" + ocr_text + "\n```\n"
        "Return ONLY a JSON object with this exact shape:\n"
        '{"store_name": "name or null", '
        '"purchased_at": "ISO 8601 datetime or null", '
        '"total_amount": number or null, "currency": "CNY", '
        '"lines": [{"raw_name": str, "quantity": number, "unit": str, '
        '"price": number, "canonical_name": str or null, '
        '"is_stock_item": bool}]}\n'
        "Rules: quantity/price are numbers, never strings. "
        "total_amount is the total printed on the receipt, NOT the sum you "
        "compute; if you cannot read it, use null. "
        "Discount lines have a negative price and is_stock_item false; "
        "bag fees / tax / service fees have is_stock_item false. "
        "One entry per printed line; keep raw_name exactly as printed." + names
    )


def _validate(parsed: dict) -> dict:
    if not isinstance(parsed, dict):
        raise QwenParseError("Qwen output is not a JSON object")
    if "lines" not in parsed or not isinstance(parsed["lines"], list):
        raise QwenParseError("Qwen output has no 'lines' list")
    for i, line in enumerate(parsed["lines"]):
        if not isinstance(line, dict):
            raise QwenParseError(f"Qwen line {i} is not an object")
        for field in ("raw_name", "quantity", "unit", "price"):
            if field not in line:
                raise QwenParseError(f"Qwen line {i} missing field {field!r}")
        if not isinstance(line["quantity"], (int, float)) or isinstance(line["quantity"], bool):
            raise QwenParseError(f"Qwen line {i} quantity is not a number")
        if not isinstance(line["price"], (int, float)) or isinstance(line["price"], bool):
            raise QwenParseError(f"Qwen line {i} price is not a number")
    if parsed.get("total_amount") is not None and not isinstance(
            parsed["total_amount"], (int, float)):
        raise QwenParseError("Qwen total_amount is not a number")
    return parsed


def parse_receipt_text(ocr_text: str,
                       canonical_names: list[str] | None = None,
                       timeout: float | None = None) -> dict:
    """One Qwen 14B call; returns the validated §6.3 dict."""
    if timeout is None:
        timeout = float(os.environ.get("QWEN_TIMEOUT_SECONDS", "120"))
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{_ollama_base_url()}/api/generate",
            json={"model": QWEN_MODEL,
                  "prompt": build_prompt(ocr_text, canonical_names),
                  "format": "json", "stream": False,
                  "options": {"temperature": 0}},
        )
    resp.raise_for_status()
    data = resp.json()
    raw = (data.get("response") or "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise QwenParseError(f"Qwen returned non-JSON output: {raw[:200]!r}")
    return _validate(parsed)
