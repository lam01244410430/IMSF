"""IMSF-v2 FastAPI application skeleton (Step 0).

Phase 1 API lives under /api/v2 (routers land in Step 1):
WeChat auth, households, receipts upload/list/detail/image/confirm.
"""

from fastapi import FastAPI

app = FastAPI(title="IMSF-v2", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


# /api/v2 routers are added in Step 1 (see app/api/).
