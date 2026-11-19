"""IMSF-v2 FastAPI application.

Phase 1 API lives under /api/v2: WeChat auth, households, receipts
upload/list/detail/image. POST .../confirm lands in Step 3.
"""

from fastapi import FastAPI

from app.api import auth, households, receipts

app = FastAPI(title="IMSF-v2", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(households.router)
app.include_router(receipts.router)
