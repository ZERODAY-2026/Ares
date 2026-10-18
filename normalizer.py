"""Safe normalization of locally generated Gemma analysis."""

from __future__ import annotations

import copy
import re


DEFAULT_FINDING = {
    "category": "other",
    "title": "Unspecified finding",
    "impact": "Impact is unclear.",
    "fact": "The agreement text requires review.",
    "quote": "",
    "page": None,
    "uncertainty": "The model did not provide enough detail.",
    "needs_legal_review": False,
}

VALID_CATEGORIES = {
    "rent", "deposit", "obligation", "right", "deadline", "termination",
    "renewal", "penalty", "maintenance", "ambiguity", "other",
}


def _short_text(value, fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _boolean(value) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "yes", "1"}
    return bool(value)


def _page_number(value):
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    return page if page > 0 else None


def normalize_finding(value) -> dict:
    """Return a predictable finding even when Gemma omits fields."""
    source = value if isinstance(value, dict) else {}
    finding = {
        key: _short_text(source.get(key), fallback)
        for key, fallback in DEFAULT_FINDING.items()
        if key not in {"page", "needs_legal_review"}
    }
    category = finding["category"].casefold()
    finding["category"] = category if category in VALID_CATEGORIES else "other"
    finding["page"] = _page_number(source.get("page"))
    finding["needs_legal_review"] = _boolean(source.get("needs_legal_review", False))
    return finding


def normalize_analysis(model_result: dict) -> dict:
    """Normalize the structured model result without hiding missing data."""
    result = copy.deepcopy(model_result or {})
    structured = result.get("structured")
    if not isinstance(structured, dict):
        raw = str(result.get("raw_output") or "").strip()
        raw = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).replace("```", "").strip()
        raw = re.sub(r"\s+", " ", raw)
        if raw:
            safe_text = raw[:500].rstrip()
            result["structured"] = {
                "summary": "Gemma returned an unstructured answer; review the text below.",
                "findings": [{
                    "category": "other",
                    "title": "Unstructured local model response",
                    "impact": "Evidence could not be verified automatically.",
                    "fact": safe_text,
                    "quote": "",
                    "page": None,
                    "uncertainty": "The response was not valid JSON, so no quotation or page was accepted.",
                    "needs_legal_review": False,
                }],
                "limitations": [
                    "Gemma returned incomplete or malformed JSON. The text is shown as unverified output."
                ],
            }
        else:
            result["structured"] = {
                "summary": "The local model returned no usable response.",
                "findings": [],
                "limitations": ["No unverified findings were shown."],
            }
        return result

    findings = structured.get("findings", [])
    if not isinstance(findings, list):
        findings = []

    limitations = structured.get("limitations", [])
    if isinstance(limitations, str):
        limitations = [limitations]
    if not isinstance(limitations, list):
        limitations = []

    structured["summary"] = _short_text(
        structured.get("summary"),
        "The model did not provide a summary.",
    )
    structured["findings"] = [normalize_finding(item) for item in findings]
    structured["limitations"] = [
        _short_text(item, "Unspecified limitation.")
        for item in limitations
    ]
    return result
