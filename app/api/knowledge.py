"""Knowledge search endpoint (Phase 2 design §5.1, §7.2).

GET /api/v2/knowledge/search — RAG lookup (debug + shelf-life screen).
Returns [{title, source, content, score}] from app.rag.search_knowledge;
no result above the similarity threshold returns [] (the client shows
"don't know" — a shelf life is never fabricated, §7.2).

Auth: JWT (require_auth) is required. NO household_id is required and
no household-membership check is done: knowledge_documents are global
reference data, not per-household (§5.1 lists no household_id for this
endpoint, unlike every household-scoped endpoint in the same table).

Phase C (contract §3): when the embedding service (Ollama) is
unreachable — the GPU host is off — the endpoint returns a controlled
503 instead of the previous 500. The success path and the []-on-no-
result behaviour are unchanged.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import Identity, require_auth
from app.rag import search_knowledge

router = APIRouter(prefix="/api/v2/knowledge", tags=["knowledge"])

TOPICS = ("shelf_life", "maintenance")


@router.get("/search")
def search(q: str | None = Query(None),
           topic: str | None = Query(None),
           k: int = Query(3),
           ident: Identity = Depends(require_auth)):
    # Query params are validated by hand (not FastAPI Query(ge/le))
    # because the design's error contract is 400 for a bad value,
    # while FastAPI's automatic validation returns 422.
    if q is None or not q.strip():
        raise HTTPException(status_code=400, detail="q is required")
    if topic is not None and topic not in TOPICS:
        raise HTTPException(
            status_code=400,
            detail="topic must be 'shelf_life' or 'maintenance'")
    if k < 1 or k > 10:
        raise HTTPException(status_code=400,
                            detail="k must be between 1 and 10")
    try:
        return search_knowledge(q.strip(), topic=topic, k=k)
    except (httpx.HTTPError, ConnectionError, OSError) as exc:
        # Embedding service unreachable (GPU off): controlled 503,
        # not a 500 (contract §3). The Ollama error itself is not
        # exposed — the detail says only that the service is offline.
        raise HTTPException(
            status_code=503,
            detail="Knowledge search unavailable:"
                   " embedding service is offline") from exc
