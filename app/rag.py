"""RAG retrieval over knowledge_documents (Phase 2 design §7, §7.3, §3.7).

Internal service only — there is no user-facing chat endpoint in
Phase 2 (§7.4). Two callers:

- ``GET /api/v2/knowledge/search`` (``app/api/knowledge.py``): debug +
  shelf-life lookup screen. Returns ``[{title, source, content,
  score}]`` with the source attached, or ``[]`` when nothing is above
  the similarity threshold — a missing answer is reported as "don't
  know", never fabricated (§7.2).
- The receipt worker (``worker/main.py``): ``shelf_life_days_for``
  supplies the RAG step of the seed > RAG > +3 expiry fallback (§7.3).

Embeddings come from Ollama ``bge-m3`` (1024 dims, D3 — Lam chốt
2026-11-20), reached through ``OLLAMA_BASE_URL`` exactly like
``app/qwen.py``. The pgvector Python package is used only to bind
vector values (``pgvector.sqlalchemy.Vector``); the migration keeps
its own minimal DDL-only ``_Vector`` so Alembic/CI never depend on
the package being importable at migration time.
"""

import json
import os
import re

import httpx
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text

from app.db import get_engine
from app.qwen import QWEN_MODEL


def _ollama_base_url() -> str:
    # Same rule as app.qwen: Ollama is reached through the SSH tunnel
    # on Oregon (127.0.0.1:11434), never at the GPU IP directly.
    return os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

EMBEDDING_MODEL = "bge-m3"  # D3, design §7.1 / §10
EMBEDDING_DIM = 1024  # bge-m3; matches knowledge_documents.embedding
SIMILARITY_THRESHOLD = 0.35  # §7.3 starting threshold (Gate E re-measures)

# Shelf-life day extraction rule (§7.3, documented here because it is a
# food-safety decision, not a formatting choice):
#  1. Deterministic regex first. A range ("3-5 days", "3–5天") uses the
#     LOWER bound — the conservative choice for food safety: the food
#     is only claimed safe for the shortest stated life. A single
#     "N days" / "N天" uses N.
#  2. Only if no number is found, Qwen 14B extracts {"days": N|null}
#     from the retrieved passage under a strict-JSON prompt.
#  3. If that fails or returns null, return None — the caller falls
#     back to +3 days (§7.3: seed > RAG > +3). A shelf life is never
#     invented: no regex hit and no Qwen number means "don't know".
_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:-|–|—|~|to)\s*(\d+(?:\.\d+)?)\s*(?:days?|天)")
_SINGLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:days?|天)")


def _embedding_timeout() -> float:
    return float(os.environ.get("EMBEDDING_TIMEOUT_SECONDS", "120"))


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed each text with Ollama bge-m3 (one /api/embeddings call each).

    Ollama's /api/embeddings takes a single ``prompt`` per call, so a
    batch is a loop, not one request. Returns one 1024-dim vector per
    input, in order. Raises on HTTP / Ollama errors — the caller
    decides whether an embedding failure is fatal (API search: 500;
    worker expiry fallback: caught and treated as "no RAG answer").
    """
    if not texts:
        return []
    timeout = _embedding_timeout()
    vectors: list[list[float]] = []
    with httpx.Client(timeout=timeout) as client:
        for item in texts:
            resp = client.post(
                f"{_ollama_base_url()}/api/embeddings",
                json={"model": EMBEDDING_MODEL, "prompt": item},
            )
            resp.raise_for_status()
            data = resp.json()
            embedding = data.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                raise RuntimeError(
                    f"Ollama {EMBEDDING_MODEL} returned no embedding")
            vectors.append([float(v) for v in embedding])
    return vectors


def search_knowledge(query: str, topic: str | None = None,
                     k: int = 3) -> list[dict]:
    """Cosine retrieval over knowledge_documents (§7.3).

    Embeds ``query`` with bge-m3, then ``ORDER BY embedding <=>
    :q`` (cosine distance) with an optional topic filter and
    ``LIMIT k``. Only rows with similarity (1 - cosine distance) >=
    ``SIMILARITY_THRESHOLD`` (0.35) are returned, best first, as
    ``{title, source, content, score}`` where ``score`` is the
    similarity. Returns ``[]`` when nothing clears the threshold.
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("query must not be empty")
    query_embedding = embed_texts([query])[0]
    sql = ("SELECT title, source, content,"
           " embedding <=> :q AS distance FROM knowledge_documents")
    params: dict = {"k": k}
    if topic is not None:
        sql += " WHERE topic = :topic"
        params["topic"] = topic
    sql += " ORDER BY distance ASC LIMIT :k"
    stmt = text(sql).bindparams(
        bindparam("q", type_=Vector(EMBEDDING_DIM)))
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(stmt, {"q": query_embedding, **params}).all()
    results = []
    for title, source, content, distance in rows:
        similarity = 1.0 - float(distance)
        if similarity < SIMILARITY_THRESHOLD:
            continue
        results.append({"title": title, "source": source,
                        "content": content, "score": similarity})
    return results


def _extract_days_from_text(content: str) -> int | None:
    """Deterministic shelf-life extraction (see the rule comment above)."""
    match = _RANGE_RE.search(content or "")
    if match:
        # Range: lower bound (conservative for food safety).
        return int(float(match.group(1)))
    match = _SINGLE_RE.search(content or "")
    if match:
        return int(float(match.group(1)))
    return None


def _extract_days_via_qwen(content: str, canonical_name: str) -> int | None:
    """Qwen 14B fallback: extract {"days": N|null} from one passage.

    Strict-JSON prompt, temperature 0. Any failure (HTTP error, bad
    JSON, null / non-positive days) returns None — never raises, so a
    bad extraction degrades to the +3 day fallback instead of failing
    the receipt job.
    """
    prompt = (
        "Extract the shelf life in days for this food from the passage"
        " below. The food is: " + canonical_name + ".\n"
        "Passage:\n```\n" + content + "\n```\n"
        'Return ONLY a JSON object with this exact shape: {"days": N or'
        ' null}. "days" is the number of days the food keeps (use the'
        " lower number if the passage gives a range); null if the"
        " passage states no shelf life in days. No other text."
    )
    try:
        timeout = float(os.environ.get("QWEN_TIMEOUT_SECONDS", "120"))
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{_ollama_base_url()}/api/generate",
                json={"model": QWEN_MODEL, "prompt": prompt,
                      "format": "json", "stream": False,
                      "options": {"temperature": 0}},
            )
        resp.raise_for_status()
        parsed = json.loads((resp.json().get("response") or "").strip())
        days = parsed.get("days") if isinstance(parsed, dict) else None
        if isinstance(days, bool) or not isinstance(days, (int, float)):
            return None
        days = int(days)
        return days if days > 0 else None
    except Exception:
        return None


def shelf_life_days_for(canonical_name: str) -> dict | None:
    """RAG shelf-life lookup for one canonical ingredient (§7.3).

    Searches topic=shelf_life for the name and takes the top result
    above the similarity threshold. Returns ``{days, source,
    content}`` or ``None`` when there is no result above threshold,
    no extractable number, or the Qwen fallback returns null/fails.
    """
    results = search_knowledge(canonical_name, topic="shelf_life", k=3)
    if not results:
        return None
    top = results[0]
    days = _extract_days_from_text(top["content"])
    if days is None:
        days = _extract_days_via_qwen(top["content"], canonical_name)
    if days is None:
        return None
    return {"days": days, "source": top["source"],
            "content": top["content"]}
