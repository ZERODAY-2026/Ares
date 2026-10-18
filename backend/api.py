"""Local FastAPI service for LegalLens document processing."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from document_processor import extract_document  # noqa: E402
from model_adapter import analyze_document, answer_question  # noqa: E402
from normalizer import normalize_analysis  # noqa: E402
from legal_retriever import retrieve_legal_context  # noqa: E402
from validator import validate_analysis  # noqa: E402

app = FastAPI(title="LegalLens Local API", version="0.1.0")

# Development frontend origin. The service remains bound to localhost when run
# using the commands in the README.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


def _usable_question(question: str, document_text: str) -> bool:
    words = re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", question.casefold())
    if len(question.strip()) < 5 or len(words) < 2:
        return False
    intent_words = {
        "what", "when", "where", "who", "why", "how", "which",
        "explain", "describe", "tell", "does", "can", "must", "is",
    }
    document_words = set(re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", document_text.casefold()))
    return bool(set(words) & intent_words or set(words) & document_words)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "LegalLens local API"}


@app.post("/api/documents/extract")
async def extract_uploaded_document(file: UploadFile = File(...)):
    """Extract an uploaded PDF/TXT file and return page-aware text."""
    filename = file.filename or "uploaded-document"
    extension = Path(filename).suffix.lower()

    if extension not in {".pdf", ".txt", ".text"}:
        raise HTTPException(status_code=415, detail="Only PDF and TXT files are supported.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        document = extract_document(data, filename)
    except ValueError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=422, detail=f"Could not extract the document: {error}") from error

    return {
        "filename": document.filename,
        "file_type": document.file_type,
        "page_count": len(document.pages),
        "nonempty_pages": document.nonempty_pages,
        "character_count": document.character_count,
        "pages": [
            {"page_number": page.page_number, "text": page.text}
            for page in document.pages
        ],
    }


@app.post("/api/documents/analyze")
async def analyze_uploaded_document(
    file: UploadFile | None = File(None),
    role: str = Form(...),
    state: str = Form("India"),
    review_context: str = Form(...),
    document_type: str = Form("Rental agreement"),
    clause_text: str = Form(""),
):
    """Extract a document and analyze it with local Gemma."""
    filename = file.filename if file else "pasted-clause.txt"
    data = await file.read() if file else b""
    if not data and not clause_text.strip():
        raise HTTPException(status_code=400, detail="Upload a document or paste a clause.")
    if not data:
        data = clause_text.encode("utf-8")

    try:
        document = extract_document(data, filename or "uploaded-document")
        legal_context = retrieve_legal_context(document.text, limit=2)
        model_result = await run_in_threadpool(
            analyze_document,
            document_text=document.text,
            role=role,
            state=state,
            review_context=review_context,
            legal_context=legal_context,
        )
        model_result = normalize_analysis(model_result)
        model_result = validate_analysis(model_result, document.pages)
        model_result["legal_context"] = legal_context
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=422, detail=f"Could not analyze the document: {error}") from error

    return {
        "filename": document.filename,
        "document_type": document_type,
        "role": role,
        "state": state,
        "review_context": review_context,
        "page_count": len(document.pages),
        "nonempty_pages": document.nonempty_pages,
        "character_count": document.character_count,
        "pages": [
            {"page_number": page.page_number, "text": page.text}
            for page in document.pages
        ],
        "analysis": model_result,
    }


@app.post("/api/chat")
async def chat_about_document(
    question: str = Form(...),
    role: str = Form("Tenant"),
    file: UploadFile | None = File(None),
    clause_text: str = Form(""),
):
    """Answer one question using only the supplied agreement and local context."""
    if not question.strip():
        raise HTTPException(status_code=400, detail="Enter a question about the document.")

    filename = file.filename if file else "pasted-clause.txt"
    data = await file.read() if file else b""
    if not data and not clause_text.strip():
        raise HTTPException(status_code=400, detail="Upload a document or paste a clause first.")
    if not data:
        data = clause_text.encode("utf-8")

    try:
        document = extract_document(data, filename or "uploaded-document")
        if not _usable_question(question, document.text):
            raise HTTPException(
                status_code=400,
                detail="Please ask a specific question about the uploaded document.",
            )
        legal_context = retrieve_legal_context(
            f"{question} {document.text}",
            limit=2,
        )
        result = await run_in_threadpool(
            answer_question,
            document_text=document.text,
            question=question,
            role=role,
            legal_context=legal_context,
        )
        raw_chat = result.get("raw_output", "")
        model_chat = result.get("structured") if isinstance(result.get("structured"), dict) else {}
        answer_text = (
            model_chat.get("answer")
            or model_chat.get("summary")
            or raw_chat.strip()
            or "The document does not provide a clear answer."
        )
        result = normalize_analysis({
            "raw_output": raw_chat,
            "structured": {
                "summary": answer_text,
                "findings": [{
                    "title": "Document answer",
                    "quote": model_chat.get("quote", ""),
                    "page": model_chat.get("page"),
                    "impact": "",
                    "fact": answer_text,
                    "uncertainty": model_chat.get("uncertainty", ""),
                }],
                "limitations": [],
            },
        })
        result["structured"] = result.get("structured")
        result = validate_analysis(result, document.pages)
        result["legal_context"] = legal_context
    except HTTPException:
        raise
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=422, detail=f"Could not answer the question: {error}") from error

    return {"question": question, "answer": result, "filename": document.filename}
