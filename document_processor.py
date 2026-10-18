"""Local document extraction for LegalLens."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pymupdf
from docx import Document


@dataclass
class DocumentPage:
    """Text extracted from one source page."""

    page_number: int
    text: str


@dataclass
class ExtractedDocument:
    """Page-aware document text retained for later evidence validation."""

    filename: str
    file_type: str
    pages: list[DocumentPage]

    @property
    def text(self) -> str:
        return "\n\n".join(
            f"[Page {page.page_number}]\n{page.text}" for page in self.pages if page.text
        )

    @property
    def character_count(self) -> int:
        return len(self.text)

    @property
    def nonempty_pages(self) -> int:
        return sum(bool(page.text.strip()) for page in self.pages)


def _clean_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\u00a0", " ").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def extract_document(data: bytes, filename: str) -> ExtractedDocument:
    """Extract PDF or TXT content locally while preserving page boundaries."""
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        pdf = pymupdf.open(stream=data, filetype="pdf")
        try:
            pages = [
                DocumentPage(index + 1, _clean_text(page.get_text("text")))
                for index, page in enumerate(pdf)
            ]
        finally:
            pdf.close()
        return ExtractedDocument(filename, "PDF", pages)

    if suffix in {".txt", ".text"}:
        text = data.decode("utf-8", errors="replace")
        raw_pages = text.split("\f")
        pages = [
            DocumentPage(index + 1, _clean_text(page))
            for index, page in enumerate(raw_pages)
        ]
        return ExtractedDocument(filename, "TXT", pages)

    if suffix == ".docx":
        try:
            word_document = Document(BytesIO(data))
        except Exception as error:
            raise ValueError(f"Could not read the DOCX file: {error}") from error

        # DOCX files do not have reliable page boundaries until Word lays them
        # out. Preserve explicit page breaks where present, and otherwise use
        # bounded text sections so the model and evidence viewer stay usable.
        sections = []
        current = []
        for paragraph in word_document.paragraphs:
            text = _clean_text(paragraph.text)
            if text:
                current.append(text)
            has_page_break = any(
                break_node.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}type") == "page"
                for run in paragraph.runs
                for break_node in run._element.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}br")
            )
            if has_page_break and current:
                sections.append("\n".join(current))
                current = []
        if current:
            sections.append("\n".join(current))

        # A long DOCX without explicit breaks is divided into local evidence
        # sections; these are labelled as pages for consistent citations.
        if len(sections) > 1:
            pages = [DocumentPage(index + 1, section) for index, section in enumerate(sections)]
        else:
            pages = []
            section_text = sections[0] if sections else ""
            for start in range(0, max(len(section_text), 1), 2800):
                pages.append(DocumentPage(len(pages) + 1, section_text[start:start + 2800]))
        return ExtractedDocument(filename, "DOCX", pages or [DocumentPage(1, "")])

    raise ValueError("Unsupported file type. Please upload a PDF, DOCX or TXT file.")
