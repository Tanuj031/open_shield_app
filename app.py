import streamlit as st
import os
import json
import tempfile
import urllib.parse
import html
import hashlib
import contextlib
import re
import importlib
import app_core as app_core_module
from app_core import (
    analyze_contract_text,
    extract_text_from_file,
    extract_text_from_image,
    compute_health_score,
    ask_contract_question,
    draft_counter_clause,
    negotiate_clause,
    generate_share_text,
    generate_pdf_report,
    LegalAnalysisResult,
)

app_core_module = importlib.reload(app_core_module)
analyze_contract_text = app_core_module.analyze_contract_text
negotiate_clause = app_core_module.negotiate_clause
generate_worst_case = app_core_module.generate_worst_case

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def safe_html(value) -> str:
    """Escape text before inserting it into unsafe_allow_html blocks."""
    return html.escape("" if value is None else str(value), quote=True)





def normalize_whatsapp_number(value: str) -> str:
    """Return digits-only WhatsApp number for wa.me links."""
    return re.sub(r"\D", "", value or "")


def cleanup_uploaded_file_buffer(uploaded_file) -> None:
    """Clear Streamlit uploaded-file references after extraction in Privacy Mode."""
    if not st.session_state.get("privacy_mode", True):
        return
    try:
        if uploaded_file and hasattr(uploaded_file, "name"):
            uploaded_file = None
            if "uploaded_file_bytes" in st.session_state:
                del st.session_state["uploaded_file_bytes"]
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="PocketLawAI — Understand Any Contract Before You Sign",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Premium CSS Styling
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* ─── Global ─── */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* ─── Hero Header ─── */
    .hero-header {
        text-align: center;
        padding: 2.5rem 1.5rem 2rem;
        margin-bottom: 2rem;
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 40%, #3b82f6 100%);
        color: white;
        border-radius: 16px;
        box-shadow: 0 20px 60px -15px rgba(15, 23, 42, 0.35);
        position: relative;
        overflow: hidden;
    }
    .hero-header::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle at 30% 50%, rgba(59, 130, 246, 0.15) 0%, transparent 60%);
        animation: pulse-glow 6s ease-in-out infinite;
    }
    @keyframes pulse-glow {
        0%, 100% { opacity: 0.5; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.05); }
    }
    .hero-header h1 {
        margin: 0;
        font-weight: 800;
        font-size: 2.5rem;
        letter-spacing: -0.03em;
        color: white !important;
        position: relative;
    }
    .hero-header .tagline {
        margin: 0.6rem 0 0 0;
        font-size: 1.1rem;
        font-weight: 400;
        opacity: 0.85;
        letter-spacing: 0.01em;
        position: relative;
    }

    /* ─── Disclaimer Banner ─── */
    .disclaimer-banner {
        background: linear-gradient(90deg, #fef3c7, #fde68a);
        border: 1px solid #f59e0b;
        border-radius: 10px;
        padding: 0.8rem 1.2rem;
        margin: 1rem 0;
        font-size: 0.88rem;
        color: #92400e;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        box-shadow: 0 2px 8px rgba(245, 158, 11, 0.12);
    }
    .disclaimer-banner strong {
        color: #78350f;
    }

    /* ─── Risk Score Meter ─── */
    .risk-meter-container {
        background: rgba(255, 255, 255, 0.6);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(226, 232, 240, 0.8);
        border-radius: 16px;
        padding: 1.8rem;
        margin: 1.5rem 0;
        text-align: center;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
    }
    .risk-score-badge {
        display: inline-block;
        padding: 0.6rem 2rem;
        border-radius: 50px;
        font-weight: 700;
        font-size: 1.3rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        margin-top: 0.6rem;
        animation: fadeInUp 0.6s ease-out;
    }
    .risk-low { background: linear-gradient(135deg, #d1fae5, #a7f3d0); color: #065f46; }
    .risk-medium { background: linear-gradient(135deg, #fef3c7, #fde68a); color: #92400e; }
    .risk-high { background: linear-gradient(135deg, #fee2e2, #fca5a5); color: #991b1b; }
    .risk-critical { background: linear-gradient(135deg, #fca5a5, #f87171); color: #7f1d1d; }
    
    .risk-bar {
        height: 10px;
        border-radius: 5px;
        background: #e2e8f0;
        margin-top: 1rem;
        overflow: hidden;
    }
    .risk-bar-fill {
        height: 100%;
        border-radius: 5px;
        transition: width 1.5s cubic-bezier(0.22, 0.61, 0.36, 1);
    }
    .risk-bar-low { width: 25%; background: linear-gradient(90deg, #10b981, #34d399); }
    .risk-bar-medium { width: 50%; background: linear-gradient(90deg, #f59e0b, #fbbf24); }
    .risk-bar-high { width: 75%; background: linear-gradient(90deg, #ef4444, #f87171); }
    .risk-bar-critical { width: 95%; background: linear-gradient(90deg, #dc2626, #ef4444); }

    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(12px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* ─── Section Headers ─── */
    .section-header {
        font-size: 1.15rem;
        font-weight: 700;
        color: #1e293b;
        padding-bottom: 0.5rem;
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 2px solid #e2e8f0;
        letter-spacing: -0.01em;
    }

    /* ─── Clause Cards ─── */
    .clause-card {
        padding: 1.2rem 1.4rem;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.7);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(226, 232, 240, 0.6);
        margin-bottom: 1rem;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .clause-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 24px rgba(0, 0, 0, 0.08);
    }
    .clause-card.risk-border-high { border-left: 5px solid #ef4444; }
    .clause-card.risk-border-medium { border-left: 5px solid #f59e0b; }
    .clause-card.risk-border-low { border-left: 5px solid #10b981; }

    .quote-text {
        font-style: italic;
        color: #475569;
        border-left: 3px solid #cbd5e1;
        padding-left: 12px;
        margin: 0.6rem 0;
        font-size: 0.92rem;
        line-height: 1.6;
    }

    /* ─── Red Flag Cards ─── */
    .red-flag-card {
        padding: 1rem 1.2rem;
        border-radius: 10px;
        background: linear-gradient(135deg, #fef2f2, #fff1f2);
        border: 1px solid #fecaca;
        margin-bottom: 0.8rem;
        box-shadow: 0 2px 8px rgba(239, 68, 68, 0.08);
    }

    /* ─── Negotiation Cards ─── */
    .negotiation-card {
        padding: 1rem 1.2rem;
        border-radius: 10px;
        background: linear-gradient(135deg, #eff6ff, #dbeafe);
        border: 1px solid #bfdbfe;
        margin-bottom: 0.8rem;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.08);
    }

    /* ─── Stats Row ─── */
    .stat-card {
        background: rgba(255, 255, 255, 0.7);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(226, 232, 240, 0.6);
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
    }
    .stat-number {
        font-size: 2rem;
        font-weight: 800;
        line-height: 1;
    }
    .stat-label {
        font-size: 0.8rem;
        color: #64748b;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.3rem;
    }

    /* ─── Health Score Card ─── */
    .health-score-card {
        border-radius: 16px;
        padding: 2rem 1.5rem;
        margin: 1.5rem 0;
        text-align: center;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.10);
        position: relative;
        overflow: hidden;
        animation: fadeInUp 0.6s ease-out;
    }
    .health-score-card::before {
        content: '';
        position: absolute;
        top: -40%; left: -40%;
        width: 180%; height: 180%;
        background: radial-gradient(circle at 30% 50%, rgba(255,255,255,0.18) 0%, transparent 60%);
        pointer-events: none;
    }
    .health-score-number {
        font-size: 3.5rem;
        font-weight: 800;
        line-height: 1;
        letter-spacing: -0.04em;
        position: relative;
    }
    .health-score-denom {
        font-size: 1.4rem;
        font-weight: 500;
        opacity: 0.7;
    }
    .health-score-label {
        font-size: 1.15rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-top: 0.4rem;
        position: relative;
    }
    .health-score-interp {
        font-size: 0.92rem;
        margin-top: 0.5rem;
        opacity: 0.85;
        position: relative;
    }

    /* ─── India Law Badge & Cards ─── */
    .india-law-badge {
        display: inline-block;
        background: linear-gradient(135deg, #ff9933, #ffffff, #138808);
        color: #1e293b;
        font-size: 0.7rem;
        font-weight: 700;
        padding: 0.15rem 0.55rem;
        border-radius: 50px;
        letter-spacing: 0.03em;
        margin-left: 0.4rem;
        vertical-align: middle;
        box-shadow: 0 1px 4px rgba(0,0,0,0.12);
    }
    .india-alert-card {
        padding: 1rem 1.2rem;
        border-radius: 10px;
        background: linear-gradient(135deg, #fef7ed, #fff7e6);
        border: 1px solid #fed7aa;
        border-left: 5px solid #f97316;
        margin-bottom: 0.8rem;
        box-shadow: 0 2px 8px rgba(249, 115, 22, 0.08);
    }
    .india-law-inline {
        background: linear-gradient(135deg, #fef7ed, #fff7e6);
        border: 1px solid #fed7aa;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        margin-top: 0.6rem;
    }
    .india-law-inline .law-name {
        font-weight: 700;
        color: #c2410c;
        font-size: 0.88rem;
    }
    .india-law-inline .law-explanation {
        font-size: 0.9rem;
        color: #475569;
        margin-top: 0.25rem;
    }

    /* Keep custom result cards readable when Streamlit switches themes. */
    .risk-meter-container,
    .clause-card,
    .red-flag-card,
    .negotiation-card,
    .stat-card,
    .india-alert-card,
    .india-law-inline {
        color: #111827 !important;
    }
    .risk-meter-container *,
    .clause-card *,
    .red-flag-card *,
    .negotiation-card *,
    .stat-card *,
    .india-alert-card *,
    .india-law-inline * {
        color: inherit;
    }
    .quote-text,
    .quote-text * {
        color: #475569 !important;
    }
    .stat-label {
        color: #64748b !important;
    }
    .india-law-inline .law-name,
    .india-alert-card .law-name {
        color: #c2410c !important;
    }

    @media (prefers-color-scheme: dark) {
        .section-header {
            color: #f8fafc !important;
            border-bottom-color: #334155;
        }
        .red-flag-card,
        .clause-card,
        .negotiation-card,
        .stat-card,
        .risk-meter-container,
        .india-alert-card,
        .india-law-inline {
            background-color: #f8fafc !important;
            color: #111827 !important;
        }
        .red-flag-card {
            background: #fff1f2 !important;
        }
        .negotiation-card {
            background: #eff6ff !important;
        }
        .india-alert-card,
        .india-law-inline {
            background: #fff7ed !important;
        }
        .clause-card {
            background: #ffffff !important;
        }
        .risk-meter-container,
        .stat-card {
            background: #ffffff !important;
        }
    }

    .neg-sim-card,
    .neg-sim-card * {
        color: var(--neg-sim-color) !important;
    }
    .neg-sim-title {
        font-size: 13px;
        font-weight: 700;
        margin: 0 0 8px;
        text-transform: uppercase;
    }
    .neg-sim-point {
        font-size: 13px;
        font-weight: 800;
        margin: 0 0 8px;
        line-height: 1.55;
    }
    .neg-sim-script {
        font-size: 13px;
        font-style: italic;
        margin: 0;
        line-height: 1.7;
    }
</style>
""", unsafe_allow_html=True)

# Chat bubble CSS (injected separately to keep the main block clean)
st.markdown("""
<style>
    /* ─── Chat Bubbles ─── */
    .chat-container {
        max-height: 500px;
        overflow-y: auto;
        padding: 0.5rem 0;
    }
    .chat-question {
        background: linear-gradient(135deg, #eff6ff, #dbeafe);
        border: 1px solid #bfdbfe;
        border-radius: 12px 12px 4px 12px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.5rem;
        max-width: 85%;
        margin-left: auto;
        font-size: 0.93rem;
        color: #1e3a5f;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.08);
    }
    .chat-answer {
        background: linear-gradient(135deg, #f0fdf4, #dcfce7);
        border: 1px solid #bbf7d0;
        border-radius: 12px 12px 12px 4px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 1rem;
        max-width: 85%;
        font-size: 0.93rem;
        color: #14532d;
        box-shadow: 0 2px 8px rgba(16, 185, 129, 0.08);
    }
    .chat-label {
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.25rem;
        opacity: 0.6;
    }

    /* ─── Counter-Clause Card ─── */
    .counter-clause-card {
        background: linear-gradient(135deg, #f0fdf4, #dcfce7);
        border: 1px solid #86efac;
        border-left: 5px solid #22c55e;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-top: 0.8rem;
        box-shadow: 0 2px 10px rgba(34, 197, 94, 0.10);
    }
    .counter-clause-label {
        font-size: 0.82rem;
        font-weight: 700;
        color: #166534;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.4rem;
    }
    .counter-clause-text {
        font-size: 0.93rem;
        color: #14532d;
        line-height: 1.65;
    }

    .chat-question,
    .chat-answer,
    .counter-clause-card {
        color: #111827 !important;
    }
    .chat-question .chat-label,
    .chat-answer .chat-label {
        color: inherit !important;
    }

    @media (prefers-color-scheme: dark) {
        .chat-question {
            background: #eff6ff !important;
            color: #1e3a5f !important;
        }
        .chat-answer,
        .counter-clause-card {
            background: #f0fdf4 !important;
            color: #14532d !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Demo Contract
# ---------------------------------------------------------------------------
MOCK_CONTRACT = """EMPLOYMENT AGREEMENT

This Employment Agreement ("Agreement") is entered into on this 1st day of July, 2026, by and between:
1. Shield Technologies Private Limited, a company incorporated under the Companies Act, 2013, having its registered office at Bengaluru, Karnataka (hereinafter "Company"); and
2. Rohan Sharma, residing at Mumbai, Maharashtra (hereinafter "Employee").

TERMS AND CONDITIONS:

1. Term and Position: The Employee shall serve as a Senior Software Engineer starting July 1, 2026.

2. Unilateral Fees and Late Payment Penalties: If the Employee fails to report to office by 9:00 AM on any working day, the Company reserves the right to levy a daily administrative penalty of INR 5,000, which will be deducted directly from the Employee's monthly salary. Furthermore, if the Employee terminates this agreement without serving the required notice period, the Employee shall pay liquidated damages of INR 10,00,000 as a penalty, which the parties agree is a genuine pre-estimate of loss.

3. Non-Compete: The Employee agrees that for a period of two (2) years following the termination of employment, the Employee shall not work for any competitor of the Company anywhere in India. The Employee acknowledges that this restriction is reasonable and necessary for the protection of the Company's business.

4. Termination and Indemnity: The Company may terminate this Agreement at any time without notice and without cause. If the Employee is terminated for cause, the Employee shall indemnify the Company for any lost profits, indirect damages, and lawyer fees up to an unlimited amount. The Employee may only terminate this agreement by giving 6 months' written notice.

5. Governing Law and Jurisdiction: This Agreement shall be governed by and construed in accordance with the laws of India. Any dispute arising out of or in connection with this Agreement shall be subject to the exclusive jurisdiction of the courts of Mumbai.
"""

# ---------------------------------------------------------------------------
# Helper: File Upload Handler
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def extract_text_from_uploaded_bytes(file_name: str, file_bytes: bytes) -> str:
    """Extract uploaded document text from cached raw bytes."""
    _, ext = os.path.splitext(file_name.lower())
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
        temp_file.write(file_bytes)
        temp_path = temp_file.name

    try:
        return extract_text_from_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass


@st.cache_data(show_spinner=False)
def extract_text_from_image_cached(image_bytes: bytes, mime_type: str, model_name: str) -> str:
    """Cache Gemini OCR for the same image/model pair across Streamlit reruns."""
    return extract_text_from_image(
        image_bytes=image_bytes,
        mime_type=mime_type,
        model_name=model_name,
    )


def get_text_from_uploaded_file(uploaded_file):
    """
    Saves an uploaded file to a temporary location, extracts its text
    using app_core's extract_text_from_file function, and cleans up.
    """
    _, ext = os.path.splitext(uploaded_file.name.lower())
    if ext not in ['.txt', '.docx', '.pdf']:
        st.error(f"Unsupported file format: {ext}. Supported: .pdf, .docx, .txt")
        return None
    if uploaded_file.size and uploaded_file.size > MAX_UPLOAD_BYTES:
        st.error("File is too large. Please upload a contract under 15 MB.")
        return None

    try:
        return extract_text_from_uploaded_bytes(uploaded_file.name, uploaded_file.getvalue())
    except Exception as e:
        st.error(f"Error parsing file: {e}")
        return None


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("""
    <div class="hero-header">
        <h1>⚖️ PocketLawAI</h1>
        <p class="tagline">Understand any contract before you sign — powered by AI</p>
    </div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.markdown("---")
privacy_mode = st.sidebar.toggle(
    "🔒 Privacy Mode",
    value=True,
    help="When enabled: masks personal information before AI analysis, "
         "and deletes uploaded files immediately after processing."
)
st.session_state["privacy_mode"] = privacy_mode

if privacy_mode:
    st.sidebar.success(
        "✅ Privacy Mode is ON\n\n"
        "Personal details are masked before analysis. "
        "Files are deleted after processing."
    )
else:
    st.sidebar.warning(
        "⚠️ Privacy Mode is OFF\n\n"
        "Raw contract text will be sent to the AI model."
    )
st.sidebar.markdown("---")

st.sidebar.markdown("### ⚖️ PocketLawAI")
st.sidebar.caption("AI-Powered Contract Analyzer for India")
st.sidebar.markdown("---")

# Model selection
model_selection = st.sidebar.selectbox(
    "🤖 AI Model",
    options=["gemini-2.5-flash-lite", "gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    index=0,
    help="gemini-2.5-flash-lite is recommended for generous free-tier limits. Use gemini-2.5-flash for higher reasoning if you have quota remaining."
)

st.sidebar.markdown("---")

# Input method — 4 options
input_option = st.sidebar.radio(
    "📄 Input Method",
    ("Upload Document", "📷 Upload Image / Scan", "Paste Contract Text", "Try Demo Contract"),
    help="Choose how you'd like to provide the contract."
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "<div style='font-size: 0.78rem; color: #94a3b8;'>"
    "⚠️ PocketLawAI is an AI tool, not a lawyer. "
    "Always consult a licensed advocate for legal advice."
    "</div>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Input Area
# ---------------------------------------------------------------------------
contract_text = ""

if input_option == "Upload Document":
    st.markdown("### 📥 Upload Your Contract")
    st.caption("Supported formats: PDF, Word (.docx), or Plain Text (.txt)")
    uploaded_file = st.file_uploader(
        "Drop your contract file here",
        type=["pdf", "txt", "docx"],
        help="Upload a contract file to analyze."
    )
    if uploaded_file is not None:
        contract_text = get_text_from_uploaded_file(uploaded_file)
        if contract_text:
            cleanup_uploaded_file_buffer(uploaded_file)
            st.success(f"✅ Successfully loaded **{uploaded_file.name}** ({len(contract_text):,} characters)")
            with st.expander("📝 Preview extracted text", expanded=False):
                st.text_area("Extracted text (editable)", value=contract_text, height=250, key="uploaded_preview")
                contract_text = st.session_state.uploaded_preview

elif input_option == "📷 Upload Image / Scan":
    st.markdown("### 📷 Upload Image / Scan")
    st.caption("Take a photo of a printed contract and upload it here. "
               "Gemini AI will read the text directly from the image.")
    uploaded_image = st.file_uploader(
        "Drop your contract photo here",
        type=["jpg", "jpeg", "png", "webp"],
        help="Supported: JPG, JPEG, PNG, WebP. Best results with a well-lit, flat photo."
    )
    if uploaded_image is not None:
        if uploaded_image.size and uploaded_image.size > MAX_UPLOAD_BYTES:
            st.error("Image is too large. Please upload a scan under 15 MB.")
            st.stop()

        # Show thumbnail preview
        st.image(uploaded_image, caption=f"📷 {uploaded_image.name}", use_container_width=True)

        # Determine MIME type
        ext = os.path.splitext(uploaded_image.name.lower())[1]
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(ext, "image/jpeg")

        if not gemini_key_configured:
            st.warning("🔑 Gemini API key is not configured. Add it to Streamlit secrets or the environment.")
        else:
            with st.spinner("📷 Reading your document image..."):
                try:
                    image_bytes = uploaded_image.getvalue()
                    contract_text = extract_text_from_image_cached(
                        image_bytes=image_bytes,
                        mime_type=mime_type,
                        model_name=model_selection,
                    )
                    cleanup_uploaded_file_buffer(uploaded_image)
                    st.success(f"✅ Extracted **{len(contract_text):,}** characters from image")
                    with st.expander("📝 Preview extracted text", expanded=False):
                        st.text_area("Extracted text (editable)", value=contract_text, height=250, key="image_preview")
                        contract_text = st.session_state.image_preview
                except ValueError as ve:
                    st.warning(f"😕 {ve}\n\nTry a well-lit, flat photo or upload a PDF instead.")
                except Exception as e:
                    st.warning(
                        "😕 We couldn't read this image clearly. "
                        "Try a well-lit, flat photo or upload a PDF instead."
                    )
                    st.caption(f"Error detail: {e}")

elif input_option == "Paste Contract Text":
    st.markdown("### ✍️ Paste Your Contract Text")
    st.caption("Copy-paste the full contract text below. English-language contracts only (v1).")
    contract_text = st.text_area(
        "Contract text",
        height=350,
        placeholder="Paste the full contract text here...",
        key="paste_input"
    )

else:  # Demo Contract
    st.markdown("### 📋 Demo Contract Mode")
    st.info("🧪 A sample Indian employment contract with intentionally risky clauses is pre-loaded below. "
            "Feel free to edit it before analyzing.")
    contract_text = st.text_area(
        "Demo contract text (editable)",
        value=MOCK_CONTRACT,
        height=350,
        key="mock_preview"
    )

# ---------------------------------------------------------------------------
# Analyze Button
# ---------------------------------------------------------------------------
st.markdown("---")
analysis_requested = st.button("🔍 Analyze Contract", type="primary", use_container_width=True)
has_saved_analysis = st.session_state.get("last_result") is not None

if not analysis_requested and has_saved_analysis:
    contract_text = st.session_state.get("contract_text", contract_text)

if analysis_requested or has_saved_analysis:
    if not contract_text or not contract_text.strip():
        st.warning("⚠️ Please provide contract text before analyzing.")
    elif analysis_requested and not gemini_key_configured:
        st.error("🔑 **Gemini API key is missing!** Add it to Streamlit secrets or set the `GEMINI_API_KEY` environment variable.")
    else:
        # ─── Disclaimer (top) ───
        st.markdown(
            '<div class="disclaimer-banner">'
            '⚠️ <strong>Disclaimer:</strong> PocketLawAI is an AI-assisted understanding tool. '
            'It does <strong>NOT</strong> provide legal advice. '
            'For binding legal opinions, consult a licensed advocate.'
            '</div>',
            unsafe_allow_html=True,
        )

        analysis_context = (
            st.spinner(f"🔍 Analyzing contract with {model_selection}... This may take up to 60 seconds.")
            if analysis_requested
            else contextlib.nullcontext()
        )

        with analysis_context:
            try:
                if analysis_requested:
                    contract_hash = hashlib.sha256(contract_text.encode("utf-8", errors="ignore")).hexdigest()
                    previous_hash = st.session_state.get("contract_hash")

                    if previous_hash != contract_hash:
                        st.session_state["chat_history"] = []
                        for key in list(st.session_state.keys()):
                            if key.startswith("counter_clause_") or key.startswith("negotiation_"):
                                del st.session_state[key]

                    if st.session_state.get("privacy_mode", True):
                        st.info(
                            "🔒 Privacy Mode: Personal information has been masked "
                            "before sending to AI."
                        )

                    result = analyze_contract_text(
                        contract_text,
                        model_name=model_selection,
                        mask_pii=st.session_state.get("privacy_mode", True),
                    )

                    # Store result in session state for export
                    st.session_state["last_result"] = result
                    st.session_state["contract_text"] = getattr(analyze_contract_text, "last_masked_text", contract_text)
                    st.session_state["contract_hash"] = contract_hash
                    st.session_state["pii_mapping"] = getattr(analyze_contract_text, "last_pii_mapping", {})
                    # Serialize analysis for Q&A context
                    st.session_state["analysis_json"] = result.model_dump_json(indent=2)

                    st.success("✅ Analysis complete!")
                else:
                    result = st.session_state["last_result"]

                # ─── 0. Contract Health Score (top-of-results hero card) ───
                health = compute_health_score(result)
                # Pick background gradient based on color band
                if health["color"] == "#10b981":  # green
                    bg_gradient = "linear-gradient(135deg, #065f46 0%, #10b981 100%)"
                    text_color = "#ffffff"
                elif health["color"] == "#f59e0b":  # amber
                    bg_gradient = "linear-gradient(135deg, #78350f 0%, #f59e0b 100%)"
                    text_color = "#ffffff"
                else:  # red
                    bg_gradient = "linear-gradient(135deg, #7f1d1d 0%, #ef4444 100%)"
                    text_color = "#ffffff"

                st.markdown(f"""
                <div class="health-score-card" style="background: {bg_gradient}; color: {text_color};">
                    <div class="health-score-number">
                        {health["score"]} <span class="health-score-denom">/ 100</span>
                    </div>
                    <div class="health-score-label">{health["label"]}</div>
                    <div class="health-score-interp">{health["interpretation"]}</div>
                </div>
                """, unsafe_allow_html=True)

                # ─── 0b. Key Terms at a Glance ───
                if hasattr(result, 'key_terms') and result.key_terms:
                    st.markdown('<div class="section-header">📋 Key Terms at a Glance</div>', unsafe_allow_html=True)

                    # Render in rows of 3
                    terms = result.key_terms[:8]  # cap at 8
                    for row_start in range(0, len(terms), 3):
                        row_terms = terms[row_start:row_start + 3]
                        cols = st.columns(3)
                        for i, term in enumerate(row_terms):
                            with cols[i]:
                                st.markdown(f"""
                                <div style="
                                    background: #F8F9FA;
                                    border: 1px solid #E0E0E0;
                                    border-radius: 10px;
                                    padding: 14px 16px;
                                    margin-bottom: 0.6rem;
                                    box-shadow: 0 1px 4px rgba(0,0,0,0.04);
                                ">
                                    <div style="
                                        font-size: 0.7rem;
                                        font-weight: 600;
                                        color: #94a3b8;
                                        text-transform: uppercase;
                                        letter-spacing: 0.08em;
                                        margin-bottom: 0.25rem;
                                    ">{safe_html(term.label)}</div>
                                    <div style="
                                        font-size: 1.05rem;
                                        font-weight: 700;
                                        color: #1e293b;
                                        line-height: 1.3;
                                    ">{safe_html(term.value)}</div>
                                </div>
                                """, unsafe_allow_html=True)

                # ─── 1. Overall Risk Score ───
                risk_lower = result.overall_risk_score.lower()
                risk_key = risk_lower if risk_lower in ("low", "medium", "high", "critical") else "medium"
                risk_emoji_map = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "🚨"}
                risk_emoji = risk_emoji_map.get(risk_key, "⚪")
                risk_css = f"risk-{risk_key}"

                st.markdown(f"""
                <div class="risk-meter-container">
                    <div style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.1em; color: #64748b; font-weight: 600;">
                        Overall Contract Risk
                    </div>
                    <div class="risk-score-badge {risk_css}">
                        {risk_emoji} {safe_html(result.overall_risk_score)}
                    </div>
                    <div style="margin-top: 0.5rem; font-size: 0.92rem; color: #475569;">
                        {safe_html(result.overall_risk_explanation)}
                    </div>
                    <div class="risk-bar">
                        <div class="risk-bar-fill risk-bar-{risk_key}"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # ─── Stats Row ───
                high_risk_count = sum(1 for c in result.clauses if c.risk_level.lower() == "high")
                med_risk_count = sum(1 for c in result.clauses if c.risk_level.lower() == "medium")
                total_clauses = len(result.clauses)

                stat_cols = st.columns(4)
                with stat_cols[0]:
                    st.markdown(f'<div class="stat-card"><div class="stat-number">{total_clauses}</div><div class="stat-label">Total Clauses</div></div>', unsafe_allow_html=True)
                with stat_cols[1]:
                    st.markdown(f'<div class="stat-card"><div class="stat-number" style="color:#ef4444">{high_risk_count}</div><div class="stat-label">High Risk</div></div>', unsafe_allow_html=True)
                with stat_cols[2]:
                    st.markdown(f'<div class="stat-card"><div class="stat-number" style="color:#f59e0b">{med_risk_count}</div><div class="stat-label">Medium Risk</div></div>', unsafe_allow_html=True)
                with stat_cols[3]:
                    st.markdown(f'<div class="stat-card"><div class="stat-number" style="color:#ef4444">{len(result.red_flags)}</div><div class="stat-label">Red Flags</div></div>', unsafe_allow_html=True)

                # ─── 2. Plain-English Summary ───
                st.markdown('<div class="section-header">📝 Plain-English Summary</div>', unsafe_allow_html=True)
                st.info(result.summary)

                # ─── 3. Red Flags + Hidden Penalties (two columns) ───
                col_left, col_right = st.columns(2)

                with col_left:
                    st.markdown(f'<div class="section-header">🚩 Red Flags ({len(result.red_flags)})</div>', unsafe_allow_html=True)
                    if not result.red_flags:
                        st.success("✅ No red-flag patterns detected.")
                    else:
                        for rf in result.red_flags:
                            sev = rf.severity.lower()
                            sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
                            st.markdown(f"""
                            <div class="red-flag-card">
                                <strong>{sev_emoji} {safe_html(rf.pattern_name)}</strong><br/>
                                <span style="font-size: 0.85rem; color: #64748b;">Clause: {safe_html(rf.clause_reference)} · Severity: {safe_html(rf.severity)}</span><br/>
                                <span style="font-size: 0.92rem;">{safe_html(rf.explanation)}</span>
                            </div>
                            """, unsafe_allow_html=True)

                with col_right:
                    st.markdown(f'<div class="section-header">💰 Hidden Penalties ({len(result.hidden_penalties)})</div>', unsafe_allow_html=True)
                    if not result.hidden_penalties:
                        st.success("✅ No hidden penalties or fees found.")
                    else:
                        for hp in result.hidden_penalties:
                            sev = hp.severity.lower()
                            sev_key = sev if sev in ("low", "medium", "high") else "medium"
                            sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
                            st.markdown(f"""
                            <div class="clause-card risk-border-{sev_key}">
                                <strong>{sev_emoji} {safe_html(hp.penalty_title)}</strong><br/>
                                <div class="quote-text">"{safe_html(hp.penalty_text.strip())}"</div>
                                <strong>Impact:</strong> {safe_html(hp.implication)}<br/>
                                <strong>Mitigation:</strong> <em>{safe_html(hp.mitigation)}</em>
                            </div>
                            """, unsafe_allow_html=True)

                # ─── 3b. India Law Alerts (above clause list) ───
                india_flagged_clauses = [c for c in result.clauses if c.india_law_flag is not None]
                if india_flagged_clauses:
                    st.markdown(f'<div class="section-header">🇮🇳 India Law Alerts ({len(india_flagged_clauses)})</div>', unsafe_allow_html=True)
                    for ic in india_flagged_clauses:
                        st.markdown(f"""
                        <div class="india-alert-card">
                            <strong>🇮🇳 Clause {ic.clause_number}: {safe_html(ic.clause_title)}</strong><br/>
                            <span class="law-name" style="font-weight: 700; color: #c2410c; font-size: 0.88rem;">
                                📜 {safe_html(ic.india_law_flag.applicable_law)}
                            </span><br/>
                            <span style="font-size: 0.9rem; color: #475569;">
                                {safe_html(ic.india_law_flag.plain_explanation)}
                            </span>
                        </div>
                        """, unsafe_allow_html=True)

                # ─── 4. Clause-by-Clause Breakdown ───
                st.markdown(f'<div class="section-header">📋 Clause-by-Clause Breakdown ({total_clauses} clauses)</div>', unsafe_allow_html=True)

                for clause in result.clauses:
                    rl = clause.risk_level.lower()
                    risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(rl, "⚪")
                    flag_badge = " 🚩" if clause.is_red_flag else ""
                    india_badge = " 🇮🇳" if clause.india_law_flag else ""
                    border_class = f"risk-border-{rl}" if rl in ("low", "medium", "high") else ""

                    with st.expander(f"{risk_icon} Clause {clause.clause_number}: {clause.clause_title} — {clause.risk_level}{flag_badge}{india_badge}", expanded=(rl == "high")):
                        st.markdown(f"""
                        <div class="clause-card {border_class}">
                            <div class="quote-text">"{safe_html(clause.clause_text.strip())}"</div>
                            <strong>Risk reason:</strong> {safe_html(clause.risk_reason)}<br/>
                        """, unsafe_allow_html=True)

                        if clause.is_red_flag and clause.red_flag_type:
                            st.markdown(f'<span style="color: #ef4444;">🚩 <strong>Red flag:</strong> {safe_html(clause.red_flag_type)}</span>', unsafe_allow_html=True)

                        if clause.india_law_flag:
                            st.markdown(f"""
                            <div class="india-law-inline">
                                <span class="india-law-badge" style="display: inline-block; background: linear-gradient(135deg, #ff9933, #ffffff, #138808); color: #1e293b; font-size: 0.7rem; font-weight: 700; padding: 0.15rem 0.55rem; border-radius: 50px;">🇮🇳 India Law Note</span>
                                <div class="law-name">📜 {safe_html(clause.india_law_flag.applicable_law)}</div>
                                <div class="law-explanation">{safe_html(clause.india_law_flag.plain_explanation)}</div>
                            </div>
                            """, unsafe_allow_html=True)

                        if clause.negotiation_suggestion:
                            st.markdown(f"""
                            <div class="negotiation-card" style="margin-top: 0.6rem;">
                                💡 <strong>Negotiation tip:</strong> {safe_html(clause.negotiation_suggestion)}
                            </div>
                            """, unsafe_allow_html=True)

                        # ─── Auto-Draft Counter-Clause (medium/high only) ───
                        if rl in ("medium", "high"):
                            cache_key = f"counter_clause_{clause.clause_number}"

                            # Show cached result if it exists
                            if cache_key in st.session_state:
                                st.markdown(f"""
                                <div class="counter-clause-card">
                                    <div class="counter-clause-label">✅ Suggested Fairer Version</div>
                                    <div class="counter-clause-text">{safe_html(st.session_state[cache_key])}</div>
                                </div>
                                """, unsafe_allow_html=True)
                                st.code(st.session_state[cache_key], language=None)
                            else:
                                # Button to trigger drafting
                                if st.button(
                                    f"✏️ Suggest Fairer Version",
                                    key=f"draft_btn_{clause.clause_number}",
                                    use_container_width=True,
                                ):
                                    with st.spinner("Drafting a fairer version..."):
                                        try:
                                            rewritten = draft_counter_clause(
                                                clause_text=clause.clause_text,
                                                risk_level=clause.risk_level,
                                                risk_reason=clause.risk_reason,
                                                model_name=model_selection,
                                            )
                                            st.session_state[cache_key] = rewritten
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ Could not draft counter-clause: {e}")

                            neg_key = f"negotiation_{clause.clause_number}"

                            if st.button(
                                "🤝 Simulate Negotiation",
                                key=f"neg_btn_{clause.clause_number}",
                                use_container_width=True,
                            ):
                                with st.spinner("Preparing your negotiation script..."):
                                    try:
                                        negotiation_result = negotiate_clause(
                                            clause_text=clause.clause_text,
                                            risk_reason=clause.risk_reason,
                                            contract_type=st.session_state.get(
                                                "contract_type", "employment"
                                            ),
                                            model_name=model_selection,
                                        )
                                        st.session_state[neg_key] = negotiation_result
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Could not generate negotiation script: {e}")

                            if neg_key in st.session_state:
                                neg = st.session_state[neg_key]

                                st.markdown("### 🤝 Negotiation Simulator")
                                col1, col2, col3 = st.columns(3)

                                your_ask = neg.get("your_ask", {})
                                company_response = neg.get("company_response", {})
                                your_counter = neg.get("your_counter", {})

                                with col1:
                                    st.markdown(
                                        f"""
                                        <div class='neg-sim-card' style='--neg-sim-color:#064E3B; background:#E8F5E9; border-radius:12px;
                                        padding:16px; border-left:4px solid #2E7D32;'>
                                        <p class='neg-sim-title'>💬 YOUR ASK</p>
                                        <p class='neg-sim-point'>
                                        {safe_html(your_ask.get("key_point", ""))}</p>
                                        <p class='neg-sim-script'>
                                        "{safe_html(your_ask.get("script", ""))}"</p>
                                        </div>
                                        """,
                                        unsafe_allow_html=True
                                    )

                                with col2:
                                    st.markdown(
                                        f"""
                                        <div class='neg-sim-card' style='--neg-sim-color:#9A3412; background:#FFF3E0; border-radius:12px;
                                        padding:16px; border-left:4px solid #E65100;'>
                                        <p class='neg-sim-title'>🏢 LIKELY RESPONSE</p>
                                        <p class='neg-sim-point'>
                                        {safe_html(company_response.get("key_point", ""))}</p>
                                        <p class='neg-sim-script'>
                                        "{safe_html(company_response.get("script", ""))}"</p>
                                        </div>
                                        """,
                                        unsafe_allow_html=True
                                    )

                                with col3:
                                    st.markdown(
                                        f"""
                                        <div class='neg-sim-card' style='--neg-sim-color:#0D47A1; background:#E3F2FD; border-radius:12px;
                                        padding:16px; border-left:4px solid #1565C0;'>
                                        <p class='neg-sim-title'>✅ YOUR COUNTER</p>
                                        <p class='neg-sim-point'>
                                        {safe_html(your_counter.get("key_point", ""))}</p>
                                        <p class='neg-sim-script'>
                                        "{safe_html(your_counter.get("script", ""))}"</p>
                                        </div>
                                        """,
                                        unsafe_allow_html=True
                                    )

                                st.info(f"💡 Bottom line: {neg.get('bottom_line', '')}")

                        st.markdown("</div>", unsafe_allow_html=True)

                # ─── 5. Top Negotiation Points ───
                if result.negotiation_points:
                    st.markdown(f'<div class="section-header">🤝 Top Negotiation Points ({len(result.negotiation_points)})</div>', unsafe_allow_html=True)
                    for np_ in result.negotiation_points:
                        st.markdown(f"""
                        <div class="negotiation-card">
                            <strong>#{np_.priority}</strong> — {safe_html(np_.point)}<br/>
                            <span style="font-size: 0.85rem; color: #64748b;">
                                Related to: {safe_html(np_.related_clause)} · {safe_html(np_.rationale)}
                            </span>
                        </div>
                        """, unsafe_allow_html=True)

                # ─── 6. Governing Law ───
                st.markdown('<div class="section-header">⚖️ Governing Law & Jurisdiction</div>', unsafe_allow_html=True)
                st.write(result.governing_law_notes)

                # ─── 7. Before You Sign ───
                st.markdown("---")
                st.markdown('<div class="section-header">⚠️ Before You Sign</div>', unsafe_allow_html=True)
                st.caption(
                    "If you sign this contract today, what is the worst thing "
                    "that can realistically happen to you?"
                )

                if st.button(
                    "🚨 Show Me The Worst Case",
                    type="primary",
                    key="worst_case_btn",
                ):
                    with st.spinner("Analyzing real-world consequences for you..."):
                        try:
                            worst_case = generate_worst_case(
                                contract_text=st.session_state["contract_text"],
                                analysis=st.session_state["last_result"],
                                model_name=model_selection,
                            )
                            st.session_state["worst_case"] = worst_case
                        except Exception as e:
                            st.error(f"Could not generate analysis: {e}")

                if "worst_case" in st.session_state:
                    wc = st.session_state["worst_case"]

                    # Header warning card
                    st.markdown(
                        """<div style='background:#FFEBEE; border-radius:12px;
                        padding:20px; border-left:5px solid #C62828; margin:16px 0;'>
                        <h3 style='color:#B71C1C; margin:0 0 8px'>
                        🚨 Worst Case Scenario If You Sign Today</h3>
                        <p style='color:#C62828; margin:0; font-size:14px'>
                        These are realistic, not hypothetical outcomes based on
                        the actual clauses in your contract.</p>
                        </div>""",
                        unsafe_allow_html=True,
                    )

                    # Consequences list
                    for i, consequence in enumerate(wc.get("consequences", []), 1):
                        severity_color = {
                            "high": "#FFEBEE",
                            "medium": "#FFF8E1",
                            "low": "#F3F4F6",
                        }
                        severity_emoji = {
                            "high": "🔴",
                            "medium": "🟡",
                            "low": "🟢",
                        }
                        sev = consequence.get("severity", "medium")
                        st.markdown(
                            f"""<div style='background:{severity_color.get(sev, "#F5F5F5")};
                            border-radius:10px; padding:16px; margin:10px 0;
                            border-left:3px solid #888;'>
                            <p style='color:#111827; font-weight:700; margin:0 0 6px; font-size:15px'>
                            {severity_emoji.get(sev, "")} {i}.
                            {consequence['headline']}</p>
                            <p style='margin:0 0 6px; font-size:13px; color:#333'>
                            {consequence['plain_explanation']}</p>
                            <p style='margin:0; font-size:12px; color:#666;
                            font-style:italic'>
                            📌 Triggered by: {consequence['clause_reference']}</p>
                            </div>""",
                            unsafe_allow_html=True,
                        )

                    # Bottom line
                    st.error(f"💬 **Bottom line:** {wc.get('bottom_line', '')}")
                    st.success(f"✅ **What you should do:** {wc.get('recommendation', '')}")

                # ─── 8. Export & Share ───
                st.markdown('<div class="section-header">📤 Share & Download</div>', unsafe_allow_html=True)

                share_col, pdf_col = st.columns(2)
                with share_col:
                    share_text = generate_share_text(result, health)
                    encoded = urllib.parse.quote(share_text)
                    whatsapp_number = st.text_input(
                        "WhatsApp number",
                        placeholder="e.g. 919876543210",
                        help="Optional. Include country code. WhatsApp does not support sending by username.",
                        key="whatsapp_number_input",
                    )
                    whatsapp_digits = normalize_whatsapp_number(whatsapp_number)
                    whatsapp_url = (
                        f"https://wa.me/{whatsapp_digits}?text={encoded}"
                        if whatsapp_digits
                        else f"https://wa.me/?text={encoded}"
                    )
                    st.markdown(
                        f'<a href="{whatsapp_url}" target="_blank" style="text-decoration: none;">'
                        f'<div style="background: linear-gradient(135deg, #128C7E, #075E54); '
                        f'color: #ffffff; border: 1px solid rgba(255,255,255,0.16); '
                        f'padding: 11px 20px; border-radius: 8px; font-size: 15px; '
                        f'font-weight: 700; cursor: pointer; text-align: center; '
                        f'margin-top: 0.35rem; box-shadow: 0 8px 18px rgba(18,140,126,0.22);">'
                        f'📤 Send Summary on WhatsApp</div></a>',
                        unsafe_allow_html=True,
                    )
                    st.caption("WhatsApp opens with the summary prefilled; you confirm and send it there.")
                with pdf_col:
                    # Spacer to vertically align with WhatsApp button
                    st.markdown('<div style="margin-top: 2.65rem;"></div>', unsafe_allow_html=True)
                    pdf_bytes = generate_pdf_report(result, health)
                    st.download_button(
                        label="⬇️ Download Summary (PDF)",
                        data=pdf_bytes,
                        file_name="pocketlawai_analysis.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )

                st.caption("Share your analysis or save it for reference before signing.")

                if st.session_state.get("privacy_mode", True):
                    pii_map = st.session_state.get("pii_mapping", {})
                    if pii_map:
                        with st.expander(
                            f"🔒 {len(pii_map)} sensitive item(s) were masked during analysis"
                        ):
                            st.caption(
                                "The following information was replaced with placeholders "
                                "before your contract was sent to the AI:"
                            )
                            for placeholder, original in pii_map.items():
                                masked_original = f"{original[:4]}{'*' * max(len(original) - 4, 0)}"
                                st.markdown(
                                    f"- `{placeholder}` → **{masked_original}**"
                                )
                            st.caption(
                                "Your actual data was never sent to the AI model."
                            )

                # ─── Disclaimer (bottom) ───
                st.markdown(
                    '<div class="disclaimer-banner" style="margin-top: 2rem;">'
                    '⚠️ <strong>Disclaimer:</strong> PocketLawAI is an AI-assisted understanding tool. '
                    'It does <strong>NOT</strong> provide legal advice. '
                    'For binding legal opinions, consult a licensed advocate.'
                    '</div>',
                    unsafe_allow_html=True,
                )

            except Exception as e:
                st.error(f"❌ An error occurred during analysis: {e}")

# ---------------------------------------------------------------------------
# Chat Q&A Section (always visible if analysis exists)
# ---------------------------------------------------------------------------
if st.session_state.get("contract_text") and st.session_state.get("analysis_json"):
    st.markdown("---")
    st.markdown('<div class="section-header">💬 Ask About Your Contract</div>', unsafe_allow_html=True)
    st.caption("Ask any question about this contract in plain English. "
               "The AI will answer based only on what the contract actually says.")

    # Initialize chat history
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    # Display chat history
    if st.session_state["chat_history"]:
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        for entry in st.session_state["chat_history"]:
            st.markdown(f"""
            <div class="chat-question">
                <div class="chat-label">🗣️ You asked</div>
                {safe_html(entry["question"])}
            </div>
            <div class="chat-answer">
                <div class="chat-label">⚖️ PocketLawAI</div>
                {safe_html(entry["answer"])}
            </div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Chat input
    with st.form(key="qa_form", clear_on_submit=True):
        user_question = st.text_input(
            "Your question",
            placeholder='e.g. "What happens if I want to leave early?"',
            label_visibility="collapsed",
        )
        col_submit, col_clear = st.columns([4, 1])
        with col_submit:
            submitted = st.form_submit_button("📨 Ask", use_container_width=True)
        with col_clear:
            clear_clicked = st.form_submit_button("🗑️ Clear Chat", use_container_width=True)

    if clear_clicked:
        st.session_state["chat_history"] = []
        st.rerun()

    if submitted and user_question and user_question.strip():
        with st.spinner("Thinking..."):
            try:
                answer = ask_contract_question(
                    question=user_question,
                    contract_text=st.session_state["contract_text"],
                    analysis_json=st.session_state["analysis_json"],
                    model_name=model_selection,
                )
                st.session_state["chat_history"].append({
                    "question": user_question,
                    "answer": answer,
                })
                st.rerun()
            except Exception as e:
                st.error(f"❌ Could not get an answer: {e}")

    # Example prompts
    if not st.session_state["chat_history"]:
        st.markdown(
            '<div style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.5rem;">'
            '💡 Try asking: '
            '"What happens if I want to leave early?" · '
            '"Can they change the rent without telling me?" · '
            '"Am I responsible if something breaks?"'
            '</div>',
            unsafe_allow_html=True,
        )
