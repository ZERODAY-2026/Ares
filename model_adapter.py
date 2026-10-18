"""Local Gemma adapter for LegalLens.

The model is invoked through the already-installed llama.cpp CLI. No document
content is sent to a remote service.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL_PATH = Path(
    os.environ.get(
        "LEGALLENS_MODEL_PATH",
        "/Users/sakshamgupta/Models/gemma-3n-E2B-it/gemma-3n-E2B-it-Q8_0.gguf",
    )
)
LLAMA_SERVER = os.environ.get(
    "LEGALLENS_LLAMA_SERVER",
    "/Users/sakshamgupta/llama.cpp/build/bin/llama-server",
)
SERVER_URL = os.environ.get("LEGALLENS_SERVER_URL", "http://127.0.0.1:8080")
_server_process = None


def build_analysis_prompt(*, document_text: str, role: str, state: str, review_context: str, legal_context: list[dict] | None = None) -> str:
    """Build a bounded, evidence-first prompt for a rental agreement."""
    # The model has a limited context window. Select the most relevant
    # page-labelled excerpts instead of sending a 20-page agreement whole.
    page_blocks = [block.strip() for block in re.split(r"(?=\[Page \d+\])", document_text) if block.strip()]
    keywords = (
        "rent deposit notice termination renewal lock-in maintenance repair "
        "penalty default payment obligation right dispute"
    ).split()
    ranked = sorted(
        page_blocks,
        key=lambda block: sum(block.lower().count(word) for word in keywords),
        reverse=True,
    )
    selected = []
    selected_chars = 0
    for block in ranked:
        if selected_chars + len(block) > 3000:
            continue
        selected.append(block)
        selected_chars += len(block)
        if selected_chars >= 2600:
            break
    bounded_text = "\n\n".join(selected) or document_text[:3000]
    legal_context = legal_context or []
    legal_text = "\n\n".join(
        f"SOURCE: {item.get('source_title', 'Unknown source')} | "
        f"SECTION: {item.get('section') or 'unknown'}\n"
        f"{str(item.get('text', ''))[:500]}"
        for item in legal_context[:2]
    ) or "No matching national legal context was retrieved."
    return f"""You are LegalLens, a cautious private rental-agreement triage assistant.
You are not a lawyer and must not determine legal enforceability.

Analyze only the relevant agreement excerpts supplied below. The user is a {role} in {state},
and is reviewing the agreement {review_context.lower()}. Other clauses may exist
outside these excerpts, so state that limitation when it matters.

Review the complete supplied text for rent, deposit, obligations, rights,
notice, termination, renewal, lock-in, maintenance, penalties and ambiguities.
Return at most 1 finding. Keep every string under 10 words.
Do not invent contract clauses, contract quotations or contract page numbers.
The legal context below is reference material, not part of the agreement.
Do not quote legal context as if it came from the agreement.
Separate explicit contract facts from cautious interpretation.
If legal context is incomplete or unverified, say so in uncertainty.
Output only one compact JSON object and no explanation outside it.

Return valid JSON only:
{{
  "summary": "one short sentence",
  "findings": [
    {{
      "category": "short category",
      "title": "short title",
      "impact": "short impact for user",
      "fact": "short explicit fact",
      "quote": "short exact quote",
      "page": 1,
      "uncertainty": "short limitation"
    }}
  ],
  "limitations": ["short limitation"]
}}

AGREEMENT TEXT:
{bounded_text}

NATIONAL LEGAL CONTEXT (REFERENCE ONLY):
{legal_text}
"""


def _extract_json(text: str) -> dict | None:
    """Extract complete JSON or safely recover complete findings if truncated."""
    decoder = json.JSONDecoder()
    answer_start = max(text.rfind("```json"), text.rfind("AGREEMENT TEXT:"))
    answer = text[answer_start:] if answer_start >= 0 else text

    # First prefer a complete response object.
    for index, char in enumerate(answer):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(answer[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and ("summary" in value or "findings" in value or "answer" in value):
            return value

    # If generation stopped before the outer object closed, preserve complete
    # finding objects rather than showing an invalid-JSON error in the UI.
    summary_match = re.search(r'"summary"\s*:\s*"((?:\\.|[^"\\])*)"', answer)
    findings_start = answer.find('"findings"')
    findings = []
    if findings_start >= 0:
        for index in range(findings_start, len(answer)):
            if answer[index] != "{":
                continue
            try:
                value, _ = decoder.raw_decode(answer[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "title" in value and "quote" in value:
                findings.append(value)

    if summary_match and findings:
        return {
            "summary": summary_match.group(1),
            "findings": findings,
            "limitations": [
                "The local model response was truncated; only complete findings are shown."
            ],
        }

    # Recover useful fields when Gemma stopped halfway through one finding or
    # added a small amount of non-JSON text around the object.
    def field(name: str) -> str:
        match = re.search(rf'"{name}"\s*:\s*"((?:\\.|[^"\\])*)"', answer)
        return match.group(1).replace('\\"', '"') if match else ""

    recovered_summary = field("summary")
    recovered = {
        "category": field("category") or "other",
        "title": field("title") or "Recovered document finding",
        "impact": field("impact") or "Impact requires review.",
        "fact": field("fact") or recovered_summary,
        "quote": field("quote"),
        "uncertainty": field("uncertainty") or "The local model response was incomplete.",
    }
    page_match = re.search(r'"page"\s*:\s*(\d+)', answer)
    if page_match:
        recovered["page"] = int(page_match.group(1))
    if recovered_summary or recovered["quote"] or recovered["fact"]:
        return {
            "summary": recovered_summary or recovered["fact"],
            "findings": [recovered],
            "limitations": [
                "The local model response was partially recovered and should be reviewed."
            ],
        }
    return None


def _server_is_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{SERVER_URL}/health", timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _ensure_server() -> None:
    global _server_process
    if _server_is_ready():
        return
    if not Path(LLAMA_SERVER).is_file():
        raise RuntimeError(f"llama-server was not found: {LLAMA_SERVER}")

    if _server_process is None or _server_process.poll() is not None:
        _server_process = subprocess.Popen(
            [
                LLAMA_SERVER,
                "-m", str(MODEL_PATH),
                "-c", "2048",
                "-t", "4",
                "--host", "127.0.0.1",
                "--port", SERVER_URL.rsplit(":", 1)[-1],
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    for _ in range(90):
        if _server_is_ready():
            return
        time.sleep(2)
    raise RuntimeError("The persistent local Gemma server did not become ready.")


def _run_server_completion(prompt: str, n_predict: int = 192) -> str:
    _ensure_server()
    payload = json.dumps({
        "prompt": prompt,
        "n_predict": n_predict,
        "temperature": 0.2,
        "cache_prompt": True,
        "stop": ["</s>"],
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{SERVER_URL}/completion",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Local Gemma server request failed: {error}") from error
    return str(result.get("content", "")).strip()


def analyze_document(*, document_text: str, role: str, state: str, review_context: str, legal_context: list[dict] | None = None) -> dict:
    """Run Gemma locally and return raw plus best-effort parsed output."""
    if not MODEL_PATH.is_file():
        raise RuntimeError(f"Gemma model was not found: {MODEL_PATH}")
    prompt = build_analysis_prompt(
        document_text=document_text,
        role=role,
        state=state,
        review_context=review_context,
        legal_context=legal_context,
    )

    raw_output = _run_server_completion(prompt, n_predict=192)
    return {"raw_output": raw_output, "structured": _extract_json(raw_output)}


def answer_question(*, document_text: str, question: str, role: str, legal_context: list[dict] | None = None) -> dict:
    """Answer one question using selected agreement excerpts and local sources."""
    page_blocks = [
        block.strip()
        for block in re.split(r"(?=\[Page \d+\])", document_text)
        if block.strip()
    ]
    question_tokens = set(re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", question.casefold()))
    ranked = sorted(
        page_blocks,
        key=lambda block: len(question_tokens & set(re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", block.casefold()))),
        reverse=True,
    )
    excerpts = []
    size = 0
    for block in ranked:
        if size + len(block) > 1800:
            continue
        excerpts.append(block)
        size += len(block)
        if size >= 1500:
            break
    agreement = "\n\n".join(excerpts) or document_text[:1800]
    legal_text = "\n".join(
        f"{item.get('source_title', 'Unknown source')}: {str(item.get('text', ''))[:300]}"
        for item in (legal_context or [])[:1]
    ) or "No legal context."
    prompt = f"""You are LegalLens, a cautious private legal document assistant.
You are not a lawyer and must not determine enforceability.
The user is a {role}. Answer only from the excerpts.
If the agreement does not answer, say so. Do not invent facts or quotes.
Return compact JSON only:
{{
  "answer": "plain-language answer",
  "quote": "short exact agreement quote or empty string",
  "page": 1,
  "uncertainty": "what remains unclear",
  "legal_context_used": false
}}

QUESTION:
{question}

AGREEMENT EXCERPTS:
{agreement}

NATIONAL LEGAL CONTEXT (REFERENCE ONLY):
{legal_text}
"""
    raw_output = _run_server_completion(prompt, n_predict=96)
    return {"raw_output": raw_output, "structured": _extract_json(raw_output)}
