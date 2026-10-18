# PS2 — Agentic AI: Private Legal Document Triage Agent

# LegalLens

**A private, local-first legal document triage and explanation assistant for Indian legal documents.**

LegalLens helps a user perform a cautious first review of an agreement without uploading the document to a cloud AI service. It extracts the document locally, retrieves relevant local legal context, asks a locally running Gemma model for a structured explanation, validates quotations against the original document, and presents the result through a React interface.

> **Important:** LegalLens provides document triage and plain-language explanations. It does not provide legal advice, determine enforceability, establish liability, or replace a qualified lawyer.

## Why LegalLens?

Legal documents are often difficult to review because important information is spread across multiple clauses. A termination question may depend on notice, default, renewal, lock-in and deposit clauses at the same time. LegalLens is designed to connect these clauses while keeping the document evidence separate from interpretation and national legal context.

The project is built around four principles:

- **Private by design:** documents and inference remain on the device.
- **Evidence first:** model quotations and pages are checked against extracted source text.
- **Fact versus interpretation:** the application distinguishes what the agreement explicitly says from possible implications.
- **Cautious assistance:** uncertainty and missing information are shown instead of being hidden.

## Current capabilities

- Upload PDF, DOCX or TXT documents.
- Paste a clause directly into the interface.
- Select a document category and role.
- Analyse rental agreements from a tenant or landlord perspective.
- Analyse employment contracts from an employee or employer perspective.
- Analyse service agreements from a client or service-provider perspective.
- Ask questions through a document-grounded chatbot.
- Retrieve national Indian legal context from a local knowledge base.
- Verify quotations and page references locally.
- Show uncertainty when the document does not provide enough information.
- Run Gemma through a persistent local `llama-server`.
- Run the complete application without an internet connection after setup.
- Switch between dark and light interface modes.

The rental-agreement workflow is currently the most developed path. Other document categories can be processed, but their specialized legal retrieval sources and evaluation coverage are still being expanded.

## Application workflow

```text
Choose document type
        ↓
Choose role
        ↓
Choose review context
        ↓
Upload PDF, DOCX or TXT / paste a clause
        ↓
Extract text locally with page or evidence sections
        ↓
Select relevant document excerpts
        ↓
Retrieve related national legal chunks locally
        ↓
Run Gemma locally through llama-server
        ↓
Normalize structured output
        ↓
Validate quotations and page references
        ↓
Show a role-aware report
        ↓
Ask follow-up questions in the local chatbot
```

## Architecture

```text
React + Vite frontend
          ↓ localhost
FastAPI local API
          ↓
PDF / DOCX / TXT extraction
          ↓
Page-aware document representation
          ↓
Keyword retrieval for contract excerpts
          ↓
Local legal retrieval from chunks.jsonl
          ↓
Persistent llama-server + Gemma GGUF
          ↓
JSON extraction and safe normalization
          ↓
Quote and page validation
          ↓
React report and chatbot
```

### Frontend

The React/Vite frontend provides:

- Document type and role selection
- PDF, DOCX and TXT upload
- Pasted-clause input
- Analysis progress indicator
- Evidence-backed findings
- Local chatbot interface
- Privacy and capability explanations
- Dark/light mode

### Backend

The FastAPI backend provides:

- `GET /api/health`
- `POST /api/documents/extract`
- `POST /api/documents/analyze`
- `POST /api/chat`

The backend performs extraction, retrieval, local inference, output normalization and evidence validation. The Gemma call runs in a worker thread so the local API remains responsive during slow CPU inference.

### Local model runtime

LegalLens uses a local Gemma 3n E2B Instruct GGUF model through `llama.cpp`:

```text
Gemma GGUF → llama-server → FastAPI → React
```

The persistent server avoids loading the approximately 4.5 GB model for every request. On an Intel i5 MacBook, Q8 inference is still CPU-intensive and may take several minutes for a full analysis.

## Document extraction

### PDF

PyMuPDF extracts text page by page and preserves page numbers for evidence validation.

### TXT

Text files are split at form-feed page markers when available. Otherwise the text is represented as a local document section.

### DOCX

`python-docx` extracts paragraphs locally. Explicit Word page breaks are preserved where available. DOCX files without reliable page boundaries are divided into bounded evidence sections so that the model and report can still use stable references.

The system does not send the original file to Gemma. Gemma receives selected extracted text with page or section labels.

## Retrieval

The current lightweight retrieval system is fully offline.

### Contract retrieval

For initial analysis, pages or document sections are ranked using rental/legal keywords such as:

```text
rent, deposit, notice, termination, renewal, lock-in,
maintenance, repair, penalty, default, payment, obligation,
right, dispute
```

For chatbot questions, the question tokens are compared with document-section tokens. The highest-overlap sections are sent to Gemma within the local context limit.

This is intentionally transparent and lightweight. A future retrieval upgrade can use BM25 or a small local embedding model.

### Legal retrieval

The local legal knowledge base is stored at:

```text
legal_knowledge_base/chunks.jsonl
```

The retriever ranks chunks using lexical overlap and preserves source metadata. Contract evidence and legal context are sent to Gemma in separate prompt sections so retrieved legal text is not presented as if it appeared in the uploaded agreement.

The current national sources include local extracts from:

- Indian Contract Act, 1872
- Registration Act, 1908
- Transfer of Property Act, 1882

Source verification and official provenance are still part of the project roadmap.

## Evidence validation

Gemma-generated evidence is not trusted automatically. For each finding, the validator checks:

1. Whether a quotation was returned.
2. Whether the cited page exists.
3. Whether the quotation appears on that page.

Findings receive statuses such as:

```text
verified
quote_not_found
invalid_page
missing_quote
```

If Gemma returns malformed or truncated JSON, LegalLens attempts partial recovery. If recovery is not possible, the raw text is shown as unverified output rather than being presented as a verified finding.

## Chatbot

The chatbot uses the same document-grounded pipeline:

```text
User question
      ↓
Relevant agreement sections selected
      ↓
Local national legal chunks retrieved
      ↓
Gemma receives bounded evidence
      ↓
Answer, quote and page extracted
      ↓
Quote validated against the document
      ↓
Answer displayed with uncertainty
```

Example questions:

- `When can the landlord terminate this agreement?`
- `What does the deposit clause mean?`
- `When is salary payable under this contract?`
- `What are the service provider's deliverables?`
- `Which clause supports this answer?`

The chatbot rejects unusable questions before calling Gemma. It also abstains when the supplied document does not provide enough evidence.

## Privacy and offline operation

After the one-time setup, the application runs through local addresses only:

```text
Frontend: 127.0.0.1:5173
Backend:  127.0.0.1:8000
Gemma:    127.0.0.1:8080
```

No cloud LLM API, remote document upload or online legal lookup is used during normal operation. The document, local legal chunks, extraction and inference remain on the device.

The one-time setup requires the Python packages, Node packages, model and legal data to already be installed. Network behaviour should still be verified independently before making absolute privacy claims.

## Installation

### Python environment

```bash
cd /Users/sakshamgupta/Desktop/Academics/hacktoberfest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Frontend dependencies

```bash
cd frontend
npm install
```

### Local model

Install or build `llama.cpp` and place the Gemma GGUF model at the path configured in `run_offline.sh`, or override it with:

```bash
export LEGALLENS_MODEL_PATH=/path/to/gemma-model.gguf
export LEGALLENS_LLAMA_SERVER=/path/to/llama-server
```

## Run everything with one command

The repository includes a launcher that starts Gemma, FastAPI and Vite together. It also clears stale listeners on the three LegalLens ports before starting.

```bash
cd /Users/sakshamgupta/Desktop/Academics/hacktoberfest
./run_offline.sh
```

Open:

```text
http://127.0.0.1:5173
```

The launcher writes local logs to:

```text
/tmp/legallens-llama.log
/tmp/legallens-api.log
/tmp/legallens-frontend.log
/tmp/legallens-offline.log
```

To run it detached from a terminal:

```bash
nohup ./run_offline.sh </dev/null >/tmp/legallens-offline.log 2>&1 &
```

To stop the local services:

```bash
for port in 8000 8080 5173; do
  pids=$(lsof -nP -tiTCP:$port -sTCP:LISTEN 2>/dev/null || true)
  [ -z "$pids" ] || kill $pids
done
```

## Prepare the legal knowledge base

The source PDFs are in `datasets/`. To regenerate local legal chunks:

```bash
source .venv/bin/activate
python prepare_rag.py
```

The output is written to:

```text
legal_knowledge_base/chunks.jsonl
```

Legal chunks should be independently checked for official provenance, current validity and jurisdiction before being treated as verified legal sources.

## Project structure

```text
.
├── backend/
│   └── api.py                          FastAPI routes
├── datasets/                           Local legal-source PDFs
├── docs/articles-research/             README image assets
├── frontend/
│   └── src/
│       ├── App.jsx                     React application
│       └── index.css                   Interface styles
├── legal_knowledge_base/
│   └── chunks.jsonl                    Local legal retrieval chunks
├── document_processor.py               PDF/DOCX/TXT extraction
├── legal_retriever.py                  Offline legal retrieval
├── model_adapter.py                    Gemma and llama-server adapter
├── normalizer.py                       Safe model-output normalization
├── validator.py                        Evidence and quotation validation
├── prepare_rag.py                      Legal knowledge-base preparation
├── requirements.txt                    Python dependencies
├── run_offline.sh                      One-command local launcher
└── README.md                           Project documentation
```

## Testing and validation status

Validated during development:

- Python module compilation
- Frontend production builds with `npm run build`
- PDF and TXT extraction
- DOCX extraction
- Malformed Gemma-output fallback
- Evidence quote and page validation
- Repeated local model requests
- Local FastAPI health endpoint
- Local Gemma health endpoint
- Offline launcher shell syntax

Remaining evaluation areas include scanned PDFs requiring OCR, complete multi-pass analysis for long agreements, comprehensive source verification, network auditing and automated end-to-end tests.

## Roadmap

1. Multi-pass analysis for every page of long documents.
2. BM25 or local semantic retrieval.
3. True conversation history for chatbot follow-up questions.
4. Better document-type-specific prompts and legal sources.
5. Evidence navigation and quote highlighting.
6. Obligation and deadline tracker.
7. OCR for scanned PDFs.
8. Source provenance and verification dates.
9. Automated privacy and network tests.
10. Browser extension for selected webpage text.

## Disclaimer

LegalLens is an informational document-triage prototype. It does not provide legal advice, determine enforceability, establish liability or replace a qualified legal professional. Legal outcomes depend on jurisdiction, current legislation, court interpretation and facts that may not be present in the uploaded document.
