"""IMSF-v2 FastAPI application.

Phase 1 API lives under /api/v2: WeChat auth, households, receipts
upload/list/detail/image. POST .../confirm lands in Step 3.
Phase 2 Step 2 adds the spending ledger (transactions + summary).
"""

from fastapi import FastAPI

from app.api import auth, households, receipts, transactions

app = FastAPI(title="IMSF-v2", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(households.router)
app.include_router(receipts.router)
app.include_router(transactions.router)
app.include_router(transactions.summary_router)
