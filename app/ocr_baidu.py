"""Baidu OCR client — 通用票据识别 (design §7, D1).

Endpoint (Baidu AI Cloud OCR docs):
- token:  POST https://aip.baidubce.com/oauth/2.0/token
  ?grant_type=client_credentials&client_id=<API_KEY>&client_secret=<SECRET_KEY>
  (confirmed in Baidu's official docs; the same URL appears in every
  Baidu OCR sample, e.g. https://ai.baidu.com/ai-doc/OCR/Pk3h7y06q)
- receipt: POST https://aip.baidubce.com/rest/2.0/ocr/v1/receipt
  ?access_token=<token>, form field ``image`` = base64 (url-encoded).
  This is the 通用票据识别 endpoint used by Baidu's official ``aip``
  SDK (``AipOcr.receipt``). NOTE: Baidu's current console also lists a
  dedicated 购物小票识别 (shopping-receipt) interface
  (https://cloud.baidu.com/doc/OCR/s/skibizxzo, updated 2026-03-31);
  its exact REST path could not be confirmed from public docs on
  2026-11-20, so this client uses the documented 通用票据识别 path
  above. Re-check the path in the Baidu console before the first live
  call with real credentials (there are none yet — see below).

Credentials come ONLY from BAIDU_API_KEY / BAIDU_SECRET_KEY. With no
keys configured the client raises BaiduNotConfiguredError — it never
fakes a success.
"""

import base64
import os
import time

import httpx

TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
# 通用票据识别 — see module docstring for the endpoint note.
RECEIPT_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/receipt"

OCR_TIMEOUT_SECONDS = float(os.environ.get("OCR_TIMEOUT_SECONDS", "25"))


class BaiduNotConfiguredError(RuntimeError):
    """Raised when BAIDU_API_KEY / BAIDU_SECRET_KEY are absent."""


class BaiduOCRClient:
    def __init__(self, api_key: str | None = None,
                 secret_key: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.api_key = api_key if api_key is not None else os.environ.get("BAIDU_API_KEY", "")
        self.secret_key = secret_key if secret_key is not None else os.environ.get("BAIDU_SECRET_KEY", "")
        self._transport = transport
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _require_keys(self) -> None:
        if not self.api_key or not self.secret_key:
            raise BaiduNotConfiguredError(
                "Baidu OCR not configured: set BAIDU_API_KEY and "
                "BAIDU_SECRET_KEY (real-name-verified Baidu AI Cloud "
                "account required; Lam's step)"
            )

    def _http(self) -> httpx.Client:
        return httpx.Client(transport=self._transport,
                            timeout=OCR_TIMEOUT_SECONDS)

    def get_access_token(self) -> str:
        self._require_keys()
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        with self._http() as client:
            resp = client.get(TOKEN_URL, params={
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.secret_key,
            })
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"Baidu token response has no access_token: {data}")
        self._token = token
        # Baidu tokens live ~30 days; cache conservatively for 1 day.
        self._token_expires_at = time.time() + 24 * 3600
        return token

    def recognize(self, image_bytes: bytes) -> dict:
        """Call 通用票据识别. Returns {"raw_text": str, "fields": dict}.

        ``raw_text`` joins every recognised line (``words_result`` items)
        in reading order; ``fields`` keeps the structured key/value pairs
        Baidu returns (e.g. total amount / store name when present).
        """
        token = self.get_access_token()
        b64 = base64.b64encode(image_bytes).decode("ascii")
        with self._http() as client:
            resp = client.post(
                RECEIPT_URL, params={"access_token": token},
                data={"image": b64},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        resp.raise_for_status()
        data = resp.json()
        if "error_code" in data:
            raise RuntimeError(
                f"Baidu OCR error {data.get('error_code')}: {data.get('error_msg')}"
            )
        lines = []
        fields: dict = {}
        for item in data.get("words_result", []) or []:
            words = item.get("words", "")
            lines.append(words)
            # Structured items carry "key" / "word" pairs in some responses.
            if "key" in item:
                fields[item["key"]] = item.get("word", "")
        # Some responses nest structured fields under "result" / "words_result_num".
        if isinstance(data.get("result"), dict):
            fields.update({k: v for k, v in data["result"].items()
                           if isinstance(v, (str, int, float))})
        return {"raw_text": "\n".join(lines), "fields": fields}
