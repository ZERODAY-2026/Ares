"""Evidence validation for LegalLens model findings.

Gemma may suggest quotations and page numbers, but only the extracted source
can establish whether that evidence is actually present.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from collections.abc import Iterable

from document_processor import DocumentPage


def _normalise(text: str) -> str:
    """Normalize whitespace and Unicode differences for safe quote matching."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", text).strip().casefold()


def _page_matches(page_value, pages: Iterable[DocumentPage]) -> list[DocumentPage]:
    try:
        page_number = int(page_value)
    except (TypeError, ValueError):
        return []
    return [page for page in pages if page.page_number == page_number]


def validate_finding(finding: dict, pages: list[DocumentPage]) -> dict:
    """Add evidence verification fields without trusting model metadata."""
    checked = copy.deepcopy(finding)
    quote = str(checked.get("quote") or "").strip()
    page_value = checked.get("page")
    matching_pages = _page_matches(page_value, pages)

    quote_normalized = _normalise(quote)
    page_quote_match = bool(
        quote_normalized
        and matching_pages
        and quote_normalized in _normalise(matching_pages[0].text)
    )

    checked["evidence_verified"] = page_quote_match
    if page_quote_match:
        checked["evidence_status"] = "verified"
    elif not quote:
        checked["evidence_status"] = "missing_quote"
    elif not matching_pages:
        checked["evidence_status"] = "invalid_page"
    else:
        checked["evidence_status"] = "quote_not_found"

    return checked


def validate_analysis(model_result: dict, pages: list[DocumentPage]) -> dict:
    """Validate all model findings against page-aware extracted text."""
    result = copy.deepcopy(model_result)
    structured = result.get("structured")

    if not isinstance(structured, dict):
        return result

    findings = structured.get("findings")
    if not isinstance(findings, list):
        structured["findings"] = []
        structured.setdefault("limitations", []).append(
            "The model returned no usable findings to validate."
        )
        return result

    structured["findings"] = [
        validate_finding(finding, pages)
        for finding in findings
        if isinstance(finding, dict)
    ]
    return result
