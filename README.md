# PS2 — Agentic AI: Private Legal Document Triage Agent

## LegalLens — Private, evidence-grounded legal document assistant

LegalLens is a local-first Legal AI application designed to help people understand legal documents in plain language. The user selects a document category, uploads a document, identifies their role, and receives a complete, role-aware analysis rather than an answer based only on an isolated question.

The current prototype focuses on **Indian residential rental agreements**. The application is designed with a broader document-assistant architecture so that the same analysis engine can support additional legal-document categories as the knowledge sources and evaluation cases are added.

> LegalLens is a document-triage and explanation tool, not a substitute for qualified legal advice. It does not determine whether a clause is legally enforceable.

## What LegalLens does

LegalLens combines three types of evidence:

1. **The uploaded agreement** — the exact clauses, amounts, dates and conditions in the user's document.
2. **Official legal context** — a locally stored and curated collection of Indian legal sources, with source and jurisdiction metadata.
3. **The user's situation** — whether the user is a tenant or landlord, the relevant state or city, and whether the document is being reviewed before signing or during a dispute.

The local Gemma model interprets the retrieved evidence, while application code validates quotations and keeps facts separate from interpretations.

## Main workflow

```text
Select document category
        ↓
Upload rental agreement
        ↓
Select role: tenant or landlord
        ↓
Provide jurisdiction and review context
        ↓
Extract the complete document locally with page references
        ↓
Identify important clauses and related clauses
        ↓
Retrieve relevant official Indian legal sources locally
        ↓
Run Gemma locally with contract and legal evidence
        ↓
Validate quotations and citations
        ↓
Generate a role-aware report
        ↓
Ask follow-up questions through the document-aware chatbot
```

The system does not analyze only the sentence related to a user's question. It reviews the agreement for connected clauses, exceptions and conditions. For example, a termination question may require checking termination, notice, breach, renewal and deposit clauses together.

## Rental-agreement analysis

The prototype analyzes the agreement from the user's selected perspective.

### Tenant perspective

- Rent and payment obligations
- Security deposit and deductions
- Notice and termination rights
- Lock-in period and early-exit consequences
- Maintenance and repair responsibilities
- Renewal and rent-increase terms
- Restrictions and penalties
- Unclear or missing protections

### Landlord perspective

- Tenant payment and maintenance obligations
- Landlord termination rights
- Notice requirements
- Breach and default conditions
- Property-use restrictions
- Subletting and occupancy conditions
- Damage, deduction and recovery provisions
- Unclear or missing protections

Each important clause is classified as relevant to the tenant, landlord, both parties, or unclear. The system explains the possible practical consequence without presenting a legal conclusion as certain.

## Report output

Each finding is designed to contain:

- Clause category
- Plain-language explanation
- What the agreement explicitly says
- Potential impact for the selected role
- Potential impact for the other party
- Possible practical consequence
- Risk or ambiguity explanation
- Exact quotation from the agreement
- Page number where available
- Relevant official legal source
- Jurisdiction and source metadata
- Missing information
- Suggested questions to clarify
- Recommendation for professional legal review when appropriate

The report distinguishes between:

- **Document fact** — directly supported by the agreement
- **Legal-source fact** — directly supported by a retrieved official source
- **Interpretation** — a cautious explanation of how the evidence may relate
- **Uncertainty** — information required before a reliable conclusion can be reached

## Conversational assistant

After the initial report, users can ask natural-language questions such as:

- “Can the landlord terminate without notice?”
- “What are my obligations as a tenant?”
- “When should the security deposit be returned?”
- “What happens if I leave during the lock-in period?”
- “Which clauses should I clarify before signing?”
- “Why was this clause marked as a concern?”

For each question, LegalLens retrieves relevant contract clauses and legal sources locally. Gemma receives those passages as evidence and produces a cautious response. The application then checks that the returned quotations exist in the original source before displaying them as verified evidence.

## Local legal knowledge system

LegalLens uses retrieval-augmented generation (RAG). RAG supplies relevant source text to Gemma at inference time; it does not retrain Gemma or assume that the model knows every current Indian law.

The legal knowledge base is intended to contain curated, traceable sources such as:

- India Code legislation
- Official Gazette notifications and amendments
- Relevant state tenancy or rent-control material
- Carefully selected official judgments where interpretation is necessary

Every legal source should include its title, jurisdiction, section, official URL, version or effective date where available, download date and verification status. The presence of an official source does not by itself prove that it applies to every agreement. State, city, tenancy type, dates and facts may change the analysis.

The repository currently includes a local preparation pipeline for extracting and chunking legal PDFs into a searchable JSON Lines knowledge base.

## Privacy and safety

LegalLens is designed for local processing:

- Uploaded agreements remain on the user's device.
- Gemma runs through a local runtime.
- Legal-source retrieval runs against a local knowledge base.
- No cloud LLM API is required.
- Document text should not be written to application logs.
- Citations are validated locally.
- The final workflow is intended to be demonstrated with network access disabled after setup.

The project must distinguish between a privacy-preserving design and a privacy claim that has actually been tested. Offline execution and network-behaviour checks are part of the verification process.

## Architecture

```text
Document selector and upload
            ↓
Local document processor
(PDF/TXT extraction, OCR or selected text)
            ↓
Page-aware clause and chunk store
            ↓
Local retrieval
(contract clauses + legal knowledge base)
            ↓
Local Gemma inference via llama.cpp
            ↓
Structured response parser
            ↓
Evidence, citation and safety validator
            ↓
Role-aware report and conversational assistant
```

The document upload, screen-region capture and browser text-selection interfaces are designed to feed the same analysis engine. The rental-agreement upload workflow is the primary prototype path and provides the complete-document context required for reliable clause analysis.

## Current repository contents

```text
.
├── datasets/
│   ├── A187209.pdf
│   ├── The_Registration_Act_1908.PDF
│   ├── The_Transfer_Of_Property_Act_1882.PDF
├── legal_knowledge_base/
│   └── chunks.jsonl
├── prepare_rag.py
└── README.md
```

`prepare_rag.py` extracts local legal PDFs, identifies likely sections, preserves page metadata and writes searchable chunks. Extracted legal text is not automatically treated as current or verified law; source provenance must be checked independently.

## Running the knowledge-base preparation script

Create and activate a Python environment, then install the required packages:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pymupdf
```

Prepare the local legal knowledge base:

```bash
python prepare_rag.py
```

The generated chunks are written to:

```text
legal_knowledge_base/chunks.jsonl
```

The exact Gemma model and local runtime must be installed separately. The target deployment is a quantized Gemma model served through `llama.cpp`, chosen to fit CPU-only inference on a constrained Intel MacBook.

## Project principles

- Read the complete agreement, not only the user's question.
- Ask for the user's role before evaluating practical impact.
- Ask for jurisdiction when legal applicability may vary.
- Separate contract wording from legal context and interpretation.
- Never invent clauses, quotations, page numbers or legal provisions.
- Treat risk as a triage signal, not a legal verdict.
- State when evidence is missing or contradictory.
- Recommend qualified legal review when the facts or law require it.
- Keep private documents and inference on the local device.

## Disclaimer

LegalLens provides informational document triage and plain-language explanations. It does not provide legal advice, determine enforceability, establish liability, or replace a qualified lawyer. Indian legal outcomes can depend on jurisdiction, current legislation, court interpretation and facts that are not present in the uploaded document.

## Project status

The repository currently contains the legal-source preparation work and the planned architecture for the local analysis engine. The implementation is being developed and evaluated against the L1–L10 hackathon requirements, including local inference, evidence grounding, uncertainty handling, role-aware analysis and demonstrable privacy.
