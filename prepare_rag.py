"""
LegalLens — local legal knowledge-base preparation.

Input:
    ./datasets/*.pdf

Outputs:
    ./legal_knowledge_base/chunks.jsonl
    ./legal_knowledge_base/extracted/extraction_report.json

Important:
- Extracted legal text is not automatically verified as current law.
- Table-of-contents chunks are retained for auditability, but should not be
  included in substantive legal retrieval.
- PDF page numbers in metadata are 1-indexed physical PDF pages.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / "datasets"
KB_DIR = ROOT / "legal_knowledge_base"
EXTRACTED_DIR = KB_DIR / "extracted"
OUTPUT_FILE = KB_DIR / "chunks.jsonl"
REPORT_FILE = EXTRACTED_DIR / "extraction_report.json"

MAX_CHARS = 2400
MIN_SECTION_CHARS = 120

# All source URLs remain unset until each file's provenance is independently
# verified against an authoritative source.
SOURCE_METADATA = {
    "A187209.pdf": {
        "title": "Indian Contract Act, 1872",
        "jurisdiction": "India",
        "source_url": None,
        "verification_status": "unverified",
    },
    "The_Registration_Act_1908.PDF": {
        "title": "Registration Act, 1908",
        "jurisdiction": "India",
        "source_url": None,
        "verification_status": "unverified",
    },
    "The_Transfer_Of_Property_Act_1882.PDF": {
        "title": "Transfer of Property Act, 1882",
        "jurisdiction": "India",
        "source_url": None,
        "verification_status": "unverified",
    },
}

# Candidate section headings must begin a line and have a conventional
# section number followed by a title. This is a heuristic, not legal parsing.
SECTION_HEADING = re.compile(
    r"""(?m)^[ \t]*
    (?P<number>\d{1,3}[A-Z]?)
    \.[ \t]+
    (?P<title>[^\n]{2,180}?)
    [ \t]*
    (?:[.—–-]|$)
    """,
    re.VERBOSE,
)

ACT_NUMBER_MARKER = re.compile(r"\bACT\s+NO\.?\s+\d+", re.IGNORECASE)
TOC_MARKER = re.compile(
    r"ARRANGEMENT\s+OF\s+SECTIONS|TABLE\s+OF\s+CONTENTS|CONTENTS",
    re.IGNORECASE,
)
PAGE_FURNITURE = [
    # Repeated source footer observed in the Transfer of Property Act PDF.
    re.compile(r"Indian\s+Kanoon\s*[-–—].*", re.IGNORECASE),
    # Repeated running title observed in the Transfer of Property Act PDF.
    re.compile(r"^\s*The\s+Transfer\s+Of\s+Property\s+Act,\s*1882\s*$", re.IGNORECASE),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_text(text: str) -> str:
    """Clean obvious extraction artifacts without stripping legal numbers."""
    text = text.replace("\u00a0", " ")
    text = text.replace("\xad", "")
    text = text.replace("\ufeff", "")
    text = text.replace("\u200b", "")

    cleaned_lines = []
    for line in text.splitlines():
        line = line.strip()

        if not line:
            cleaned_lines.append("")
            continue

        if any(pattern.match(line) for pattern in PAGE_FURNITURE):
            continue

        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_toc_pages(pages):
    """
    Identify likely table-of-contents pages conservatively.

    Once a contents marker appears, pages are treated as TOC until the Act's
    formal number marker appears. If no formal marker exists, only pages
    containing an explicit contents marker are labelled TOC.
    """
    toc_pages = set()
    toc_started = False
    formal_act_started = False

    for page_index, raw_text in enumerate(pages):
        text = raw_text or ""

        if ACT_NUMBER_MARKER.search(text):
            formal_act_started = True
            toc_started = False
            continue

        if formal_act_started:
            continue

        if TOC_MARKER.search(text):
            toc_started = True

        if toc_started:
            toc_pages.add(page_index + 1)

    # For PDFs without an Act-number marker, avoid classifying the entire
    # document as TOC. Retain only pages with explicit TOC markers.
    if not formal_act_started:
        toc_pages = {
            i + 1
            for i, text in enumerate(pages)
            if TOC_MARKER.search(text or "")
        }

    return toc_pages


def split_long_text(text: str, max_chars: int = MAX_CHARS):
    """Split long section text near paragraph or sentence boundaries."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    parts = []
    remaining = text

    while len(remaining) > max_chars:
        window = remaining[:max_chars]
        split_at = max(
            window.rfind("\n\n"),
            window.rfind(". "),
            window.rfind("; "),
        )

        # Avoid tiny chunks when no useful boundary is available.
        if split_at < int(max_chars * 0.55):
            split_at = max_chars

        else:
            # Keep the punctuation/paragraph separator with the preceding chunk.
            split_at += 1

        part = remaining[:split_at].strip()
        if part:
            parts.append(part)
        remaining = remaining[split_at:].strip()

    if remaining:
        parts.append(remaining)

    return parts


def pages_for_span(page_spans, start, end):
    """Return physical PDF page numbers intersecting [start, end)."""
    found = []
    for page_number, page_start, page_end in page_spans:
        if page_end > start and page_start < end:
            found.append(page_number)

    if not found:
        return None, None

    return min(found), max(found)


def make_chunk(
    *,
    source_id,
    source_title,
    source_file,
    source_url,
    jurisdiction,
    section,
    section_title,
    page_start,
    page_end,
    content_type,
    text,
    chunk_number,
    extraction_method="pymupdf",
    verification_status="unverified",
):
    safe_section = section if section is not None else "na"
    return {
        "chunk_id": (
            f"{source_id[:16]}_s{safe_section}_p{page_start}-{page_end}"
            f"_c{chunk_number}"
        ),
        "source_id": source_id,
        "source_title": source_title,
        "source_file": source_file,
        "source_url": source_url,
        "jurisdiction": jurisdiction,
        "section": section,
        "section_title": section_title,
        "page_start": page_start,
        "page_end": page_end,
        "content_type": content_type,
        "text": text,
        "extraction_method": extraction_method,
        "verification_status": verification_status,
    }


def process_pdf(pdf_path: Path):
    print(f"\nProcessing: {pdf_path.name}")

    source_meta = SOURCE_METADATA.get(
        pdf_path.name,
        {
            "title": pdf_path.stem.replace("_", " "),
            "jurisdiction": None,
            "source_url": None,
            "verification_status": "unverified",
        },
    )

    source_id = sha256_file(pdf_path)[:16]
    warnings = []

    with pymupdf.open(pdf_path) as document:
        raw_pages = [page.get_text("text") or "" for page in document]

    print(f"Pages: {len(raw_pages)}")

    empty_pages = [
        page_number
        for page_number, text in enumerate(raw_pages, start=1)
        if len(text.strip()) < 20
    ]
    for page_number in empty_pages:
        warnings.append({
            "file": pdf_path.name,
            "page": page_number,
            "issue": "Very little extractable text; page may need visual/OCR review.",
        })

    toc_pages = detect_toc_pages(raw_pages)
    if toc_pages:
        print(f"Likely table-of-contents pages: {sorted(toc_pages)}")

    chunks = []
    chunk_counter = 0

    # Keep TOC pages as auditable records, but mark them distinctly so retrieval
    # can exclude them.
    for page_number in sorted(toc_pages):
        page_text = clean_text(raw_pages[page_number - 1])
        if not page_text:
            continue

        for piece in split_long_text(page_text):
            chunk_counter += 1
            chunks.append(make_chunk(
                source_id=source_id,
                source_title=source_meta["title"],
                source_file=pdf_path.name,
                source_url=source_meta["source_url"],
                jurisdiction=source_meta["jurisdiction"],
                section=None,
                section_title=None,
                page_start=page_number,
                page_end=page_number,
                content_type="table_of_contents",
                text=piece,
                chunk_number=chunk_counter,
                verification_status=source_meta["verification_status"],
            ))

    # Build one text stream from non-TOC pages and retain page offsets so chunks
    # can cite the original physical PDF pages.
    page_spans = []
    stream_parts = []
    cursor = 0

    for page_number, raw_text in enumerate(raw_pages, start=1):
        if page_number in toc_pages:
            continue

        page_text = clean_text(raw_text)
        if not page_text:
            continue

        if stream_parts:
            stream_parts.append("\n\n")
            cursor += 2

        start = cursor
        stream_parts.append(page_text)
        cursor += len(page_text)
        page_spans.append((page_number, start, cursor))

    stream = "".join(stream_parts).strip()

    if not stream:
        warnings.append({
            "file": pdf_path.name,
            "issue": "No substantive text remained after TOC separation and cleanup.",
        })
        return chunks, warnings, {
            "file": pdf_path.name,
            "title": source_meta["title"],
            "sha256": sha256_file(pdf_path),
            "page_count": len(raw_pages),
            "toc_pages": sorted(toc_pages),
            "chunk_count": len(chunks),
            "source_url": source_meta["source_url"],
            "jurisdiction": source_meta["jurisdiction"],
            "verification_status": source_meta["verification_status"],
        }

    headings = list(SECTION_HEADING.finditer(stream))

    # Keep front matter before the first detected section as a separate chunk.
    if not headings:
        warnings.append({
            "file": pdf_path.name,
            "issue": "No statutory section headings detected; review extraction manually.",
        })
        start_page, end_page = pages_for_span(page_spans, 0, len(stream))
        for part_number, piece in enumerate(split_long_text(stream), start=1):
            chunk_counter += 1
            chunks.append(make_chunk(
                source_id=source_id,
                source_title=source_meta["title"],
                source_file=pdf_path.name,
                source_url=source_meta["source_url"],
                jurisdiction=source_meta["jurisdiction"],
                section=None,
                section_title=None,
                page_start=start_page or 1,
                page_end=end_page or len(raw_pages),
                content_type="unclassified_text",
                text=piece,
                chunk_number=chunk_counter,
                verification_status=source_meta["verification_status"],
            ))
    else:
        first_heading_start = headings[0].start()
        front_matter = stream[:first_heading_start].strip()

        if front_matter:
            start_page, end_page = pages_for_span(
                page_spans, 0, first_heading_start
            )
            for piece in split_long_text(front_matter):
                chunk_counter += 1
                chunks.append(make_chunk(
                    source_id=source_id,
                    source_title=source_meta["title"],
                    source_file=pdf_path.name,
                    source_url=source_meta["source_url"],
                    jurisdiction=source_meta["jurisdiction"],
                    section=None,
                    section_title=None,
                    page_start=start_page or 1,
                    page_end=end_page or start_page or 1,
                    content_type="preamble_or_unclassified_text",
                    text=piece,
                    chunk_number=chunk_counter,
                    verification_status=source_meta["verification_status"],
                ))

        for index, heading in enumerate(headings):
            section_start = heading.start()
            section_end = (
                headings[index + 1].start()
                if index + 1 < len(headings)
                else len(stream)
            )
            section_text = stream[section_start:section_end].strip()

            section_number = heading.group("number").strip()
            section_title = heading.group("title").strip().rstrip(" .—–-")
            page_start, page_end = pages_for_span(
                page_spans, section_start, section_end
            )

            if not page_start:
                page_start = 1
            if not page_end:
                page_end = page_start

            if len(section_text) < MIN_SECTION_CHARS:
                warnings.append({
                    "file": pdf_path.name,
                    "section_candidate": section_number,
                    "page_start": page_start,
                    "page_end": page_end,
                    "issue": (
                        "Very short section candidate; could be a genuine short "
                        "provision, a contents/footnote artifact, or a detection error. "
                        "Inspect manually."
                    ),
                })

            pieces = split_long_text(section_text)
            for piece_number, piece in enumerate(pieces, start=1):
                chunk_counter += 1
                chunks.append(make_chunk(
                    source_id=source_id,
                    source_title=source_meta["title"],
                    source_file=pdf_path.name,
                    source_url=source_meta["source_url"],
                    jurisdiction=source_meta["jurisdiction"],
                    section=section_number,
                    section_title=section_title,
                    page_start=page_start,
                    page_end=page_end,
                    content_type="statutory_section_candidate",
                    text=piece,
                    chunk_number=piece_number,
                    verification_status=source_meta["verification_status"],
                ))

    if pdf_path.name == "The_Transfer_Of_Property_Act_1882.PDF":
        warnings.append({
            "file": pdf_path.name,
            "issue": (
                "Source text identifies itself as a 2003 version and says the "
                "original publication could not be verified. Do not treat it as "
                "verified current law."
            ),
        })

    source_record = {
        "file": pdf_path.name,
        "title": source_meta["title"],
        "sha256": sha256_file(pdf_path),
        "page_count": len(raw_pages),
        "toc_pages": sorted(toc_pages),
        "chunk_count": sum(1 for c in chunks if c["source_file"] == pdf_path.name),
        "source_url": source_meta["source_url"],
        "jurisdiction": source_meta["jurisdiction"],
        "verification_status": source_meta["verification_status"],
    }

    return chunks, warnings, source_record


def main():
    if not PDF_DIR.exists():
        raise SystemExit(
            f"PDF input directory not found: {PDF_DIR}\n"
            "Create ./datasets and place your PDFs there."
        )

    pdf_files = sorted(
        path for path in PDF_DIR.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    )

    if not pdf_files:
        raise SystemExit(f"No PDF files found in {PDF_DIR}")

    KB_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    all_chunks = []
    all_warnings = []
    source_manifest = []

    for pdf_path in pdf_files:
        chunks, warnings, source_record = process_pdf(pdf_path)
        all_chunks.extend(chunks)
        all_warnings.extend(warnings)
        source_manifest.append(source_record)

    # Write one JSON object per line.
    with OUTPUT_FILE.open("w", encoding="utf-8") as handle:
        for chunk in all_chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_directory": str(PDF_DIR),
        "output_file": str(OUTPUT_FILE),
        "total_sources": len(source_manifest),
        "total_chunks": len(all_chunks),
        "retrieval_note": (
            "For substantive legal retrieval, exclude chunks whose "
            "content_type is 'table_of_contents'. Review unclassified and "
            "short-section warnings manually."
        ),
        "sources": source_manifest,
        "warnings": all_warnings,
    }

    with REPORT_FILE.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    print("\nFinished.")
    print(f"PDFs processed: {len(source_manifest)}")
    print(f"Chunks written: {len(all_chunks)}")
    print(f"Warnings: {len(all_warnings)}")
    print(f"Dataset: {OUTPUT_FILE}")
    print(f"Report: {REPORT_FILE}")
    print("All sources remain marked unverified.")


if __name__ == "__main__":
    main()
