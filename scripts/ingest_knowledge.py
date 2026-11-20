"""Ingest knowledge documents for RAG (Phase 2 design §7.3).

Usage:
    python scripts/ingest_knowledge.py --file <jsonl> --topic <shelf_life|maintenance>

Each JSONL row is {topic, source, title, content,
canonical_ingredient_id?, equipment_type?} — the source-agnostic
format from §7.2: any licensed source must be converted to this
format first; there is no per-website parser here, and no web
scraping. The row's ``topic`` (when present) wins over --topic;
--topic is the default and is validated the same way.

Steps per row: clean the text (strip HTML tags/entities, normalise
whitespace) -> split content > 2000 chars into multiple rows ->
embed in batches of 10 via app.rag (bge-m3) -> INSERT into
knowledge_documents.

Dedup: migration 0003 has NO unique index on content (design §7.3
says "UNIQUE on hash of content" but 0003 did not create one), so
dedup happens here at the application level — a row whose normalised
content already exists in the table (or earlier in this run) is
skipped and counted, never inserted twice.

After the FIRST ingest (table was empty before this run and at least
one row was inserted), the script runs
``REINDEX INDEX ix_knowledge_documents_embedding``: the ivfflat
index is only useful once rows exist (§3.7).

DATABASE_URL comes from the environment, exactly like the app.
This script is NOT run against the live DB by the Step 5 worker —
the coordinator runs the ingest.
"""

import argparse
import html
import json
import logging
import os
import re
import sys
import uuid
from pathlib import Path

# Allow `python scripts/ingest_knowledge.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pgvector.sqlalchemy import Vector  # noqa: E402
from sqlalchemy import bindparam, text  # noqa: E402

from app.db import get_engine  # noqa: E402
from app.rag import EMBEDDING_DIM, embed_texts  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout)
log = logging.getLogger("imsf-v2-ingest")

TOPICS = ("shelf_life", "maintenance")
MAX_CHUNK_CHARS = 2000
EMBED_BATCH = 10
IVFFLAT_INDEX = "ix_knowledge_documents_embedding"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(raw: str) -> str:
    """Strip HTML tags/entities and normalise whitespace (§7.3)."""
    no_tags = _TAG_RE.sub(" ", raw or "")
    return _WS_RE.sub(" ", html.unescape(no_tags)).strip()


def split_content(content: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split content > limit chars into multiple rows (§7.3).

    Breaks at the last whitespace at or before the limit so words are
    not cut in half; a single over-long word is hard-cut at the limit.
    """
    if len(content) <= limit:
        return [content]
    chunks: list[str] = []
    rest = content
    while len(rest) > limit:
        cut = rest.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        chunks.append(rest)
    return [c for c in chunks if c]


def _parse_uuid(value):
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def load_rows(path: str, default_topic: str) -> tuple[list[dict], int]:
    """Read + clean + split the JSONL file. Returns (rows, skipped)."""
    rows: list[dict] = []
    skipped = 0
    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("line %d: invalid JSON, skipped: %s",
                            line_no, exc)
                skipped += 1
                continue
            if not isinstance(raw, dict):
                log.warning("line %d: not an object, skipped", line_no)
                skipped += 1
                continue
            topic = raw.get("topic") or default_topic
            if topic not in TOPICS:
                log.warning("line %d: bad topic %r, skipped",
                            line_no, topic)
                skipped += 1
                continue
            source = (raw.get("source") or "").strip()
            content = clean_text(raw.get("content") or "")
            if not source or not content:
                log.warning("line %d: missing source/content, skipped",
                            line_no)
                skipped += 1
                continue
            title = (raw.get("title") or "").strip() or None
            canon = _parse_uuid(raw.get("canonical_ingredient_id"))
            if raw.get("canonical_ingredient_id") and canon is None:
                log.warning("line %d: bad canonical_ingredient_id,"
                            " stored as NULL", line_no)
            equipment_type = (raw.get("equipment_type") or "").strip() or None
            chunks = split_content(content)
            for i, chunk in enumerate(chunks):
                chunk_title = title
                if len(chunks) > 1 and title:
                    chunk_title = f"{title} (part {i + 1}/{len(chunks)})"
                rows.append({
                    "topic": topic, "source": source,
                    "title": chunk_title, "content": chunk,
                    "canonical_ingredient_id": canon,
                    "equipment_type": equipment_type,
                    # Dedup key: the normalised content itself.
                    "norm_content": chunk,
                })
    return rows, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest RAG knowledge documents (design §7.3).")
    parser.add_argument("--file", required=True,
                        help="JSONL file of knowledge rows")
    parser.add_argument("--topic", required=True, choices=list(TOPICS),
                        help="default topic for rows without one")
    args = parser.parse_args()

    rows, skipped_bad = load_rows(args.file, args.topic)
    log.info("loaded %d rows (%d skipped as invalid) from %s",
             len(rows), skipped_bad, args.file)
    if not rows:
        log.info("nothing to ingest")
        return 0

    engine = get_engine()
    insert_stmt = text(
        "INSERT INTO knowledge_documents (topic, source, title,"
        " content, embedding, canonical_ingredient_id, equipment_type)"
        " VALUES (:topic, :source, :title, :content, :emb,"
        " :canon, :equip)"
    ).bindparams(bindparam("emb", type_=Vector(EMBEDDING_DIM)))

    ingested = 0
    skipped_dup = 0
    with engine.begin() as conn:
        was_empty = conn.execute(
            text("SELECT COUNT(*) FROM knowledge_documents")
        ).scalar_one() == 0
        # Application-level dedup (§7.3 note in this file's docstring):
        # there is no content-hash unique index in migration 0003.
        seen: set[str] = {
            row[0] for row in conn.execute(
                text("SELECT content FROM knowledge_documents")).all()
        }
        for start in range(0, len(rows), EMBED_BATCH):
            batch = rows[start:start + EMBED_BATCH]
            fresh = []
            for row in batch:
                if row["norm_content"] in seen:
                    skipped_dup += 1
                    continue
                seen.add(row["norm_content"])
                fresh.append(row)
            if not fresh:
                continue
            vectors = embed_texts([r["content"] for r in fresh])
            params = [{
                "topic": r["topic"], "source": r["source"],
                "title": r["title"], "content": r["content"],
                "emb": vec, "canon": r["canonical_ingredient_id"],
                "equip": r["equipment_type"],
            } for r, vec in zip(fresh, vectors)]
            conn.execute(insert_stmt, params)
            ingested += len(fresh)
            log.info("ingested %d rows so far (batch %d-%d)",
                     ingested, start + 1, start + len(batch))
        if was_empty and ingested > 0:
            # ivfflat needs data before it is useful (§3.7).
            conn.execute(text(f"REINDEX INDEX {IVFFLAT_INDEX}"))
            log.info("reindexed %s (first ingest)", IVFFLAT_INDEX)
    log.info("done: ingested=%d skipped_duplicate=%d skipped_invalid=%d",
             ingested, skipped_dup, skipped_bad)
    print(f"ingested={ingested} skipped_duplicate={skipped_dup}"
          f" skipped_invalid={skipped_bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
