"""LegalLens local prototype UI.

Step 2 milestone: upload a PDF/TXT rental agreement and extract it locally
with page references. AI analysis is intentionally not mocked here.
"""

import streamlit as st

from document_processor import ExtractedDocument, extract_document


st.set_page_config(
    page_title="LegalLens | Private Legal Document Triage",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root { --ink: #e8eefc; --muted: #a7b4cc; --panel: rgba(21, 31, 54, .78); }
    .stApp {
        background: radial-gradient(circle at 80% 0%, #1a3561 0, #0c1425 42%, #070b14 100%);
        color: var(--ink);
    }
    [data-testid="stSidebar"] { background: rgba(8, 14, 28, .92); }
    .hero {
        padding: 2.1rem 2.4rem 1.7rem; border: 1px solid rgba(128,170,255,.18);
        border-radius: 24px; background: linear-gradient(120deg, rgba(18,35,67,.92), rgba(18,25,45,.62));
        box-shadow: 0 20px 70px rgba(0,0,0,.22); margin-bottom: 1.2rem;
    }
    .eyebrow { color: #83b8ff; text-transform: uppercase; letter-spacing: .16em; font-size: .72rem; font-weight: 700; }
    .hero h1 { margin: .25rem 0 .35rem; font-size: 2.6rem; letter-spacing: -.05em; }
    .hero p { color: var(--muted); max-width: 720px; font-size: 1.02rem; }
    .scene {
        min-height: 245px; border-radius: 24px; position: relative; overflow: hidden;
        background: radial-gradient(circle at 50% 42%, rgba(83,164,255,.26), transparent 28%), #0b1426;
        border: 1px solid rgba(114,174,255,.25); display: flex; align-items: center; justify-content: center;
    }
    .scene:before, .scene:after { content: ""; position: absolute; border: 1px solid rgba(105,178,255,.26); border-radius: 50%; animation: pulse 4s ease-in-out infinite; }
    .scene:before { width: 210px; height: 210px; }
    .scene:after { width: 290px; height: 290px; animation-delay: 1.1s; }
    .document {
        z-index: 2; width: 112px; height: 145px; border-radius: 9px; padding: 20px 15px;
        background: linear-gradient(145deg, #f3f7ff, #b8d5ff); transform: rotate(-7deg);
        box-shadow: 12px 18px 35px rgba(0,0,0,.38); animation: float 4s ease-in-out infinite;
    }
    .line { height: 5px; margin: 10px 0; border-radius: 5px; background: #6b8fbd; opacity: .75; }
    .line.short { width: 62%; }
    @keyframes float { 0%,100% { transform: rotate(-7deg) translateY(4px); } 50% { transform: rotate(-3deg) translateY(-8px); } }
    @keyframes pulse { 0%,100% { transform: scale(.92); opacity: .35; } 50% { transform: scale(1.04); opacity: .7; } }
    .panel { padding: 1.1rem 1.2rem; border-radius: 18px; background: var(--panel); border: 1px solid rgba(137,170,220,.16); }
    .panel h3 { margin-top: 0; }
    .status { color: #8de2bd; font-weight: 650; }
    .caption { color: var(--muted); font-size: .86rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">PS2 · Agentic AI · Private by design</div>
      <h1>LegalLens</h1>
      <p>Understand the complete agreement, see how clauses affect your role, and ask evidence-backed questions without sending your document to the cloud.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## Document context")
    document_type = st.selectbox(
        "Document type",
        ["Rental agreement", "Employment contract", "Service agreement", "Legal notice"],
    )
    role = st.selectbox("Your role", ["Tenant", "Landlord", "Employee", "Employer", "Other"])
    state = st.text_input("State / city", placeholder="e.g. Karnataka, Bengaluru")
    review_context = st.selectbox(
        "Review context",
        ["Before signing", "Already signed", "During a dispute", "General understanding"],
    )
    st.divider()
    st.markdown('<p class="status">● Local processing design</p>', unsafe_allow_html=True)
    st.caption("The uploaded document is processed by this local application. AI inference will be connected after the extraction milestone.")

left, right = st.columns([1.15, 1], gap="large")

with left:
    st.markdown("### Start a private review")
    uploaded_file = st.file_uploader(
        "Upload your document",
        type=["pdf", "txt"],
        help="PDF text extraction preserves physical page numbers. TXT files can use form-feed characters to separate pages.",
    )

    if uploaded_file is None:
        st.markdown(
            '<div class="panel"><h3>Document workspace</h3><p class="caption">Upload a rental agreement to begin. LegalLens will first extract the complete document locally before generating any analysis.</p></div>',
            unsafe_allow_html=True,
        )
    else:
        if st.button("Extract document locally", type="primary", use_container_width=True):
            try:
                extracted = extract_document(uploaded_file.getvalue(), uploaded_file.name)
                st.session_state["extracted_document"] = extracted
                st.session_state["document_context"] = {
                    "type": document_type,
                    "role": role,
                    "location": state,
                    "review_context": review_context,
                }
                st.success("Document extracted locally.")
            except ValueError as error:
                st.error(str(error))
            except Exception as error:
                st.error(f"The document could not be processed: {error}")

with right:
    st.markdown("### Local document view")
    st.markdown(
        '<div class="scene"><div class="document"><div class="line"></div><div class="line"></div><div class="line short"></div><div class="line"></div><div class="line short"></div></div></div>',
        unsafe_allow_html=True,
    )
    st.caption("The animated document is a visual status layer. Legal findings will always appear as readable text with source evidence.")

extracted_document: ExtractedDocument | None = st.session_state.get("extracted_document")
if extracted_document:
    st.divider()
    st.markdown("### Extraction result")
    metrics = st.columns(3)
    metrics[0].metric("File", extracted_document.filename)
    metrics[1].metric("Pages", len(extracted_document.pages))
    metrics[2].metric("Characters", f"{extracted_document.character_count:,}")

    empty_pages = len(extracted_document.pages) - extracted_document.nonempty_pages
    if empty_pages:
        st.warning(f"{empty_pages} page(s) contained no extractable text. Scanned pages may require local OCR.")

    for page in extracted_document.pages:
        with st.expander(f"Page {page.page_number}", expanded=page.page_number == 1):
            st.text(page.text or "No extractable text on this page.")

    st.divider()
    st.markdown("### Document assistant")
    st.info("The chatbot will use the complete extracted agreement, your selected role and relevant legal sources. Local Gemma inference is the next integration milestone.")
    st.chat_input("Ask about your agreement…", disabled=True)
