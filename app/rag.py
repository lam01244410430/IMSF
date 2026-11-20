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
# food-safety decision, not a formatting choice). CORRECTED 2026-11-21
# (parent decision): this is a FRIDGE system, so the extraction prefers
# the span associated with REFRIGERATION:
#  1. Deterministic regex first. Every span is "N [unit]" or a range
#     "N-M [unit]" (unit: days/weeks/months/years, or 天/周/月/年).
#     A range uses the LOWER bound — the conservative choice for food
#     safety: the food is only claimed safe for the shortest stated
#     life. Units convert to days: week = 7, month = 30, year = 365
#     (month = 30 follows the codebase's own convention — the Beko
#     maintenance passage writes "once a month, 30 days").
#  2. Span selection: each span is classified by the storage keyword
#     NEAREST to it (before or after) inside a window around the span:
#     "refrigerat*" -> fridge, "freez*" -> freezer, "pantry" ->
#     pantry, "room temperature" -> room. The FIRST fridge span wins.
#     If there is no fridge span, the FIRST span that is NOT a freezer
#     span wins (pantry / room / other). A freezer span is NEVER
#     returned: the freezer life (months) is far longer than the
#     fridge life, and returning it for a fridge item would be unsafe
#     (e.g. milk: "Freeze 3 months" with no fixed fridge number ->
#     None, not 90 days). No number is ever invented: the value always
#     comes from a span in the passage itself.
#  3. Only if no number is found, Qwen 14B extracts {"days": N|null}
#     from the retrieved passage under a strict-JSON prompt (the
#     prompt asks for the REFRIGERATED life, consistent with this
#     rule).
#  4. If that fails or returns null, return None — the caller falls
#     back to +3 days (§7.3: seed > RAG > +3). A shelf life is never
#     invented: no regex hit and no Qwen number means "don't know".
_UNIT_DAYS = {"day": 1, "days": 1, "天": 1,
              "week": 7, "weeks": 7, "周": 7,
              "month": 30, "months": 30, "月": 30,
              "year": 365, "years": 365, "年": 365}
_SPAN_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:(?:-|–|—|~|to)\s*(\d+(?:\.\d+)?)\s*)?"
    r"(days?|weeks?|months?|years?|天|周|月|年)")
_STORAGE_KEYWORDS = (
    (re.compile(r"refrigerat", re.IGNORECASE), "fridge"),
    (re.compile(r"freez", re.IGNORECASE), "freezer"),
    (re.compile(r"pantry", re.IGNORECASE), "pantry"),
    (re.compile(r"room temperature", re.IGNORECASE), "room"),
)
# Characters searched around a span for its storage keyword. The
# storage verb is normally adjacent to the span ("refrigerate 3-5
# days", "6 months in the refrigerator"); the classifier below uses
# the span's own slot (see _span_contexts), not a fixed window, so
# these constants are no longer used for the window size.
def _is_decimal_point(content: str, pos: int) -> bool:
    """True if the "." at pos is a decimal point (digit on both sides)."""
    return (content[pos] == "." and 0 < pos < len(content) - 1
            and content[pos - 1].isdigit() and content[pos + 1].isdigit())


def _prev_clause_end(content: str, pos: int) -> int:
    """Index just after the last ";" or "." (non-decimal) before pos."""
    idx = 0
    for m in re.finditer(r"[;.]", content[:pos]):
        if _is_decimal_point(content, m.start()):
            continue
        idx = m.end()
    return idx


def _next_clause_start(content: str, pos: int) -> int:
    """Index of the first ";" or "." (non-decimal) at/after pos."""
    for m in re.finditer(r"[;.]", content[pos:]):
        if _is_decimal_point(content, pos + m.start()):
            continue
        return pos + m.start()
    return len(content)


def _span_contexts(content: str,
                   spans: list[tuple[int, int]]) -> list[str]:
    """Storage context of each span, in document order.

    A span's slot is the text around it bounded by the neighbouring
    spans and by clause delimiters (";" / "."): the before-slot runs
    from the previous span's end (or clause start) to this span, the
    after-slot from this span to the next span's start (or clause
    end). A storage keyword inside a slot is attributed to that span;
    each keyword occurrence is used at most once, in document order,
    so a keyword that completes an earlier span (e.g. "1 year in the
    pantry") is not re-used for the next span ("6 months in the
    refrigerator"). Returns one of "fridge", "freezer", "pantry",
    "room", or "other" (no keyword in the slot) per span.
    """
    keywords: list[tuple[int, int, str]] = []
    for pattern, ctx in _STORAGE_KEYWORDS:
        for m in pattern.finditer(content):
            keywords.append((m.start(), m.end(), ctx))
    keywords.sort()
    used: set[tuple[int, int]] = set()
    contexts: list[str] = []
    for i, (s, e) in enumerate(spans):
        prev_end = spans[i - 1][1] if i > 0 else 0
        next_start = spans[i + 1][0] if i + 1 < len(spans) else len(content)
        before_lo = max(prev_end, _prev_clause_end(content, s))
        after_hi = min(next_start, _next_clause_start(content, e))
        best: tuple[int, int, int, str] | None = None  # (dist, ks, ke, ctx)
        for ks, ke, ctx in keywords:
            if (ks, ke) in used:
                continue
            if before_lo <= ks and ke <= s:
                dist = s - ke
            elif e <= ks and ke <= after_hi:
                dist = ks - e
            else:
                continue
            if best is None or dist < best[0]:
                best = (dist, ks, ke, ctx)
        if best is None:
            contexts.append("other")
        else:
            used.add((best[1], best[2]))
            contexts.append(best[3])
    return contexts


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
    """Deterministic shelf-life extraction (see the rule comment above).

    Prefers the first REFRIGERATED span; else the first span that is
    not a freezer span; else None (Qwen fallback). A range uses its
    lower bound, converted to days by unit. A span that truncates to
    0 days (e.g. "0.5 days") is skipped, not returned.
    """
    text = content or ""
    found: list[tuple[int, int, int]] = []  # (start, end, days)
    for m in _SPAN_RE.finditer(text):
        lower = float(m.group(1))
        days = int(lower * _UNIT_DAYS[m.group(3)])
        if days <= 0:
            continue
        found.append((m.start(), m.end(), days))
    if not found:
        return None
    contexts = _span_contexts(text, [(s, e) for s, e, _ in found])
    spans: list[tuple[int, str]] = [(d, c) for (_, _, d), c in zip(found, contexts)]
    for days, ctx in spans:
        if ctx == "fridge":
            return days
    for days, ctx in spans:
        if ctx != "freezer":
            return days
    return None


def _extract_days_via_qwen(content: str, canonical_name: str) -> int | None:
    """Qwen 14B fallback: extract {"days": N|null} from one passage.

    Strict-JSON prompt, temperature 0. Any failure (HTTP error, bad
    JSON, null / non-positive days) returns None — never raises, so a
    bad extraction degrades to the +3 day fallback instead of failing
    the receipt job.
    """
    prompt = (
        "Extract the REFRIGERATED shelf life in days for this food"
        " from the passage below. The food is: " + canonical_name + ".\n"
        "Passage:\n```\n" + content + "\n```\n"
        'Return ONLY a JSON object with this exact shape: {"days": N or'
        ' null}. "days" is the number of days the food keeps in the'
        " refrigerator (use the lower number if the passage gives a"
        " range for refrigeration; convert weeks/months/years to days:"
        " 1 week = 7 days, 1 month = 30 days, 1 year = 365 days); null"
        " if the passage states no refrigerated shelf life in days (do"
        " not use the freezer or pantry life). No other text."
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
