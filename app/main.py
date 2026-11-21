"""IMSF FastAPI application.

Phase 1 API lives under /api/v2: WeChat auth, households, receipts
upload/list/detail/image. POST .../confirm lands in Step 3.
Phase 2 Step 2 adds the spending ledger (transactions + summary).
Phase 2 Step 4 adds equipments + maintenance logs.
Phase 2 Step 5 adds knowledge search (RAG, design §7).
"""

from fastapi import FastAPI

from app.api import (auth, equipments, fridge, households, knowledge,
                     notifications, receipts, recipes, shopping_lists,
                     transactions)

app = FastAPI(title="IMSF", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(households.router)
app.include_router(receipts.router)
app.include_router(transactions.router)
app.include_router(transactions.summary_router)
app.include_router(fridge.router)
app.include_router(notifications.router)
app.include_router(shopping_lists.router)
app.include_router(recipes.router)
app.include_router(equipments.router)
app.include_router(knowledge.router)
