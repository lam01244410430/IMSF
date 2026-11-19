"""Qwen-VL fallback OCR (design §7 fallback) + OCR provider switch.

``qwen-vl`` calls the qwen2.5vl:7b model on Ollama (reached through the
SSH tunnel on 127.0.0.1:11434) with a transcription prompt and returns
the receipt text. ``mock`` returns canned OCR text for the synthetic
Step-2 fixture receipt (tests only). All providers return the same
shape: {"raw_text": str, "fields": dict}.
"""

import base64
import os

import httpx

from app.ocr_baidu import BaiduNotConfiguredError, BaiduOCRClient

VL_MODEL = "qwen2.5vl:7b"
VL_PROMPT = (
    "Transcribe ALL text visible on this shopping receipt, line by line, "
    "exactly as printed, in the original language (Chinese). Keep every "
    "number, price and quantity exactly. Do not add explanations, do not "
    "summarise, do not guess missing text — output only the transcribed "
    "lines."
)

# Canned OCR text for the synthetic fixture receipt
# (tests/fixtures/synthetic_receipt.png). Used ONLY by OCR_PROVIDER=mock.
MOCK_OCR_TEXT = """永辉超市
2026-11-20 09:12
农夫山泉 550ml 2瓶 4.00
鸡蛋 1盒 12.80
大米 5kg 1袋 32.50
青菜 1斤 6.80
合计 56.10"""


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def qwen_vl_transcribe(image_bytes: bytes,
                       timeout: float | None = None) -> dict:
    """Transcribe a receipt image with qwen2.5vl:7b via Ollama /api/generate."""
    if timeout is None:
        timeout = float(os.environ.get("QWEN_TIMEOUT_SECONDS", "120"))
    b64 = base64.b64encode(image_bytes).decode("ascii")
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{_ollama_base_url()}/api/generate",
            json={"model": VL_MODEL, "prompt": VL_PROMPT,
                  "images": [b64], "stream": False,
                  "options": {"temperature": 0}},
        )
    resp.raise_for_status()
    data = resp.json()
    text = (data.get("response") or "").strip()
    if not text:
        raise RuntimeError("Qwen-VL returned empty transcription")
    return {"raw_text": text, "fields": {}}


def run_ocr(image_bytes: bytes, provider: str | None = None) -> dict:
    """Run OCR with the configured provider.

    provider: "baidu" | "qwen-vl" | "mock" (env OCR_PROVIDER, default baidu).
    Raises BaiduNotConfiguredError for baidu without credentials.
    """
    if provider is None:
        provider = os.environ.get("OCR_PROVIDER", "baidu")
    if provider == "baidu":
        return BaiduOCRClient().recognize(image_bytes)
    if provider == "qwen-vl":
        return qwen_vl_transcribe(image_bytes)
    if provider == "mock":
        return {"raw_text": MOCK_OCR_TEXT, "fields": {}}
    raise ValueError(f"Unknown OCR_PROVIDER: {provider!r} "
                     "(expected baidu | qwen-vl | mock)")
