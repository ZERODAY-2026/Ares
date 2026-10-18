"""Small, offline keyword retriever for the national legal knowledge base."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHUNKS_FILE = ROOT / "legal_knowledge_base" / "chunks.jsonl"


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", (text or "").casefold()))


def load_chunks() -> list[dict]:
    if not CHUNKS_FILE.is_file():
        return []
    chunks = []
    with CHUNKS_FILE.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            if chunk.get("content_type") == "table_of_contents":
                continue
            if chunk.get("text"):
                chunks.append(chunk)
    return chunks


def retrieve_legal_context(query: str, limit: int = 3) -> list[dict]:
    """Return national legal chunks ranked by simple lexical overlap."""
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    scored = []
    for chunk in load_chunks():
        text_tokens = _tokens(
            " ".join(
                str(chunk.get(field) or "")
                for field in ("source_title", "section_title", "text")
            )
        )
        overlap = query_tokens & text_tokens
        if not overlap:
            continue
        score = len(overlap)
        # Prefer chunks with a statutory section and verified sources when
        # those metadata fields become available.
        if chunk.get("section"):
            score += 1
        if chunk.get("verification_status") == "verified":
            score += 2
        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, chunk in scored[:limit]:
        results.append({
            "source_title": chunk.get("source_title"),
            "source_file": chunk.get("source_file"),
            "source_url": chunk.get("source_url"),
            "jurisdiction": chunk.get("jurisdiction", "India"),
            "section": chunk.get("section"),
            "section_title": chunk.get("section_title"),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
            "text": chunk.get("text"),
            "verification_status": chunk.get("verification_status", "unverified"),
            "retrieval_score": score,
        })
    return results
