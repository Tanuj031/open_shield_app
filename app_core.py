import os
import base64
import html as html_lib
import re
import json
from google import genai
from pydantic import BaseModel, Field
from typing import List, Optional
import docx2txt

try:
    import markdown as md_lib
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False

# ---------------------------------------------------------------------------
# Pydantic Schemas — Structured output for the Gemini analysis
# ---------------------------------------------------------------------------

class IndiaLawFlag(BaseModel):
    """India-specific legal concern for a clause."""
    applicable_law: str = Field(description="The specific Indian law, section, or act that applies (e.g. 'Section 27, Indian Contract Act 1872')")
    plain_explanation: str = Field(description="Plain-English explanation of why this clause is problematic under Indian law and what the user should know")


class ClauseAnalysis(BaseModel):
    """Individual clause broken out from the contract with risk scoring."""
    clause_number: int = Field(description="Sequential clause number (1-indexed)")
    clause_title: str = Field(description="Short title for this clause (e.g. 'Termination', 'Non-Compete')")
    clause_text: str = Field(description="The exact text or snippet from the contract for this clause")
    risk_level: str = Field(description="Risk level: Low, Medium, or High")
    risk_reason: str = Field(description="One-line plain-English reason for the risk score, understandable by a non-lawyer")
    is_red_flag: bool = Field(description="True if this clause matches a known red-flag pattern")
    red_flag_type: Optional[str] = Field(default=None, description="If is_red_flag is True, the pattern name (e.g. 'Auto-renewal trap', 'One-sided termination', 'Excessive penalty', 'Vague liability', 'Missing notice period', 'Broad non-compete', 'Uncapped indemnity')")
    negotiation_suggestion: Optional[str] = Field(default=None, description="For Medium/High risk clauses: a polite, practical ask the user could raise with the other party")
    india_law_flag: Optional[IndiaLawFlag] = Field(default=None, description="If this clause violates or is unusual under a specific Indian law, provide the applicable law and a plain-English explanation. Omit (set to null) if no India-specific concern applies.")


class RedFlag(BaseModel):
    """A specific red-flag pattern detected in the contract."""
    pattern_name: str = Field(description="Name of the red-flag pattern (e.g. 'One-sided termination', 'Auto-renewal trap')")
    clause_reference: str = Field(description="Which clause(s) this flag relates to (e.g. 'Clause 4: Termination')")
    severity: str = Field(description="Severity: High, Medium, or Low")
    explanation: str = Field(description="Plain-English explanation of why this is a red flag and its real-world impact")


class HiddenPenalty(BaseModel):
    """A hidden charge, fee, or financial penalty buried in the contract."""
    penalty_title: str = Field(description="Title or description of the penalty/charge")
    penalty_text: str = Field(description="The exact text or snippet describing the penalty, fee, or liability")
    severity: str = Field(description="Severity: High, Medium, or Low")
    implication: str = Field(description="Description of the financial or operational impact, noting if it is hidden in boilerplates or complex terms")
    mitigation: str = Field(description="Proposed mitigation or pushback strategy")


class NegotiationPoint(BaseModel):
    """A top actionable negotiation suggestion the user can raise before signing."""
    priority: int = Field(description="Priority rank (1 = most important)")
    point: str = Field(description="A polite, practical sentence the user can say or propose to the other party")
    related_clause: str = Field(description="Which clause this relates to (e.g. 'Clause 4: Termination')")
    rationale: str = Field(description="Brief reason why this negotiation point matters")


class KeyTerm(BaseModel):
    """A key factual term extracted from the contract."""
    label: str = Field(description="Short term name (e.g. 'Salary', 'Notice Period', 'Security Deposit')")
    value: str = Field(description="The actual value from the contract (e.g. '₹6,00,000 per annum', '30 days')")


class LegalAnalysisResult(BaseModel):
    """Complete structured analysis of a legal contract."""
    summary: str = Field(description=(
        "A clear, jargon-free summary (4-6 sentences, written at a Class 10 reading level) covering: "
        "what the contract is, who the parties are, core obligations of each side, key dates or durations, "
        "and any standout terms. No legal jargon without an inline explanation."
    ))
    overall_risk_score: str = Field(description="Aggregate risk assessment: Low, Medium, High, or Critical")
    overall_risk_explanation: str = Field(description="One-sentence justification for the overall risk score")
    clauses: List[ClauseAnalysis] = Field(description="Every clause in the contract, individually scored and analysed")
    red_flags: List[RedFlag] = Field(description=(
        "Specific known red-flag patterns found in the contract. Patterns to look for: "
        "auto-renewal traps, one-sided termination, excessive penalty clauses, vague liability language, "
        "missing notice periods, broad non-compete, uncapped indemnity, unilateral amendment rights, "
        "intellectual property grab, exclusive jurisdiction in a distant city."
    ))
    hidden_penalties: List[HiddenPenalty] = Field(description="Hidden charges, penalties, unilateral fees, or uncapped liabilities found in the agreement")
    negotiation_points: List[NegotiationPoint] = Field(description="Top 3-5 actionable negotiation suggestions ranked by priority")
    governing_law_notes: str = Field(description="Key observations regarding the governing law, jurisdiction, and compliance under Indian contract laws")
    key_terms: List[KeyTerm] = Field(default_factory=list, description=(
        "Up to 8 key factual terms extracted from the contract. Each has a short label and the actual value. "
        "Only include terms with concrete values mentioned in the contract. "
        "Examples by type — Employment: Salary, Notice Period, Probation Period, Bond Period, Non-Compete Duration; "
        "Rental: Monthly Rent, Security Deposit, Lock-in Period, Maintenance Charges; "
        "Freelance: Project Fee, Payment Terms, Deadline, IP Ownership; "
        "NDA: Confidentiality Period, Scope, Governing Law."
    ))


def get_api_key() -> str:
    """
    Reads Gemini API key from Streamlit secrets (cloud) 
    or .env file (local development).
    """
    import streamlit as st
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        return os.environ.get("GEMINI_API_KEY", "")

# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------

def get_client() -> genai.Client:
    """
    Initializes and returns the GenAI client.
    """
    api_key = get_api_key()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set. Please set it before running.")
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Text Extraction (TXT, DOCX, PDF)
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_path: str) -> str:
    """Extracts text from a PDF file using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "pdfplumber is required for PDF support. "
            "Install it with: pip install pdfplumber"
        )
    
    pages_text = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text and text.strip():
                pages_text.append(text.strip())
    
    if not pages_text:
        raise ValueError(
            "Could not extract any text from the PDF. "
            "The file may be scanned or image-based. "
            "Try uploading it via the Image Upload option instead."
        )
    
    return "\n\n".join(pages_text)


def extract_text_from_file(file_path: str) -> str:
    """
    Extracts text content from a file path.
    Supports .txt, .docx, and .pdf files.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
        
    _, ext = os.path.splitext(file_path.lower())
    
    if ext == '.pdf':
        return extract_text_from_pdf(file_path)
    elif ext == '.docx':
        try:
            return docx2txt.process(file_path)
        except Exception as e:
            raise ValueError(f"Error parsing .docx file: {str(e)}")
    elif ext in ('.txt', '.md', '.json'):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            raise ValueError(f"Error reading text file: {str(e)}")
    else:
        raise ValueError(f"Unsupported file format: {ext}. Supported: .pdf, .docx, .txt")


# ---------------------------------------------------------------------------
# Image Text Extraction via Gemini Vision
# ---------------------------------------------------------------------------

IMAGE_EXTRACT_PROMPT = (
    "This is a photo of a printed legal contract. "
    "Extract ALL the text from this image exactly as written. "
    "Return only the extracted text, nothing else. "
    "Preserve paragraph structure and clause numbering."
)


def extract_text_from_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    model_name: str = "gemini-2.0-flash",
) -> str:
    """
    Send a contract image directly to Gemini's vision capability
    and extract the text content. No external OCR library needed.
    
    Args:
        image_bytes: Raw bytes of the uploaded image.
        mime_type: MIME type (image/jpeg, image/png, image/webp).
        model_name: Gemini model to use (must support vision).
    
    Returns:
        Extracted text from the image.
    
    Raises:
        ValueError: If Gemini cannot read the image or returns empty text.
    """
    client = get_client()

    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    response = client.models.generate_content(
        model=model_name,
        contents=[
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data,
                        }
                    },
                    {
                        "text": IMAGE_EXTRACT_PROMPT,
                    },
                ],
            }
        ],
    )

    extracted = response.text.strip() if response.text else ""

    if not extracted:
        raise ValueError(
            "Could not extract any text from the image. "
            "The image may be too blurry, dark, or not a contract."
        )

    return extracted


# ---------------------------------------------------------------------------
# Contract Analysis via Gemini
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are **PocketLawAI**, an expert Indian Legal Advisor and Contract Analyst with deep \
knowledge of the Indian Contract Act (1872), labour laws, rent control acts, IT Act, and \
standard corporate/commercial/employment contract practices in India.

You are a legal assistant specializing in Indian contract law. \
When analyzing clauses, specifically check for violations or red flags \
under the following Indian legal frameworks:

- **Indian Contract Act, 1872**: unconscionable terms, unilateral changes, \
agreements void or voidable under Indian law
- **Specific Relief Act, 1963**: clauses that seek remedies Indian courts \
typically don't grant
- **State-level Rent Control Acts**: rental agreements missing mandatory \
notice periods, illegal lock-in terms, excessive security deposits \
beyond 2 months which courts often disallow
- **Employment law**: bond/training bonds that Indian courts have held \
unenforceable if the penalty is unreasonable; non-competes which are \
void post-employment under Section 27 of the Indian Contract Act
- **Service/freelance agreements**: missing TDS clause under Section 194J, \
missing GST liability allocation

For any clause that violates or is unusual under Indian law specifically, \
populate the `india_law_flag` field on that clause object with:
- `applicable_law`: the specific section/act (e.g. "Section 27, Indian Contract Act 1872")
- `plain_explanation`: a plain-English explanation of the concern

If no Indian law concern applies to a clause, set `india_law_flag` to null \
for that clause.

Your task is to analyse the provided contract text thoroughly and return a structured JSON response.

## Instructions

### 1. Plain-English Summary
Write a 4-6 sentence summary at roughly a Class 10 reading level. Cover:
- What is this contract about?
- Who are the parties?
- What are the core obligations of each party?
- Key dates, durations, or financial terms?
- Any standout or unusual terms?
Do NOT use legal jargon without an inline plain-English explanation.

### 2. Overall Risk Score
Assign an overall risk score: **Low**, **Medium**, **High**, or **Critical**.
Provide a one-sentence justification.

### 3. Clause-by-Clause Breakdown
Break the contract into individual clauses. For EACH clause:
- Assign a risk level: Low (🟢), Medium (🟡), or High (🔴)
- Write a one-line plain-English risk reason
- Mark `is_red_flag = true` if it matches any known red-flag pattern
- If `is_red_flag` is true, specify the `red_flag_type`
- For Medium/High risk clauses, suggest a polite, practical negotiation ask

### 4. Red-Flag Highlighting
Separately list ALL detected red-flag patterns. Specifically look for:
- Auto-renewal traps
- One-sided termination (only one party can terminate, or without notice)
- Excessive penalty clauses (liquidated damages acting as penalties, contrary to Section 74)
- Vague liability language (unlimited liability, blanket indemnification)
- Missing notice periods
- Broad non-compete clauses (likely unenforceable under Section 27)
- Uncapped indemnity
- Unilateral amendment rights
- Intellectual property grabs
- Exclusive jurisdiction in a distant or inconvenient city

### 5. Hidden Penalties & Fees
List any hidden charges, unilateral fees, compounding late fees, or uncapped liabilities \
that may not be immediately obvious on a first read.

### 6. Negotiation Suggestions
Provide the top 3-5 actionable, polite negotiation points the user could raise before signing. \
Rank by priority. Each should be a practical sentence like: \
"Ask for a mutual 30-day notice period instead of immediate one-sided termination."

### 7. Governing Law & Jurisdiction
Note the governing law, jurisdiction (courts, arbitration clauses), and any compliance \
observations under Indian law.

### 8. Key Terms Extraction
Extract the most important factual terms from the contract and return them as a \
`key_terms` array. Each item should have a `label` (short term name) and `value` \
(the actual value from the contract).

Extract only terms that have a concrete value mentioned in the contract. \
Common examples by contract type:
- Employment: Salary, Notice Period, Probation Period, Leave Policy, Bond Period, \
Bond Penalty, Non-Compete Duration, Health Insurance, Joining Date
- Rental: Monthly Rent, Security Deposit, Lock-in Period, Notice Period, \
Maintenance Charges, Rent Escalation
- Freelance/Service: Project Fee, Payment Terms, Deadline, Penalty for Delay, \
IP Ownership, Revision Limit
- NDA: Confidentiality Period, Scope of Confidentiality, Governing Law, Jurisdiction

Return a maximum of 8 key terms. If a term is not mentioned, do not include it. \
Return only terms with actual values.

## Response Format
Respond strictly with valid JSON conforming to the requested schema. \
Ensure all analysis is tailored to Indian legal frameworks and practices.\
"""


def mask_sensitive_info(text: str) -> tuple[str, dict]:
    """
    Masks sensitive PII in contract text before sending to AI.
    Returns masked text and a mapping of placeholders to originals.
    """
    mapping = {}
    counter = {"n": 0}

    def replace(label: str, value: str) -> str:
        placeholder = f"[{label}_{counter['n']}]"
        counter["n"] += 1
        mapping[placeholder] = value
        return placeholder

    # Email addresses (before phone to avoid partial matches)
    emails = re.findall(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        text
    )
    for email in set(emails):
        text = text.replace(email, replace("EMAIL", email))

    # Indian phone numbers (10 digit, with/without +91)
    phones = re.findall(
        r'(?:\+91[\s-]?)?[6-9]\d{9}\b',
        text
    )
    for phone in set(phones):
        text = text.replace(phone, replace("PHONE", phone))

    # Indian PAN card numbers
    pans = re.findall(r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b', text)
    for pan in set(pans):
        text = text.replace(pan, replace("PAN_NUMBER", pan))

    # Aadhaar numbers (12 digit)
    aadhaars = re.findall(r'\b\d{4}\s?\d{4}\s?\d{4}\b', text)
    for aadhaar in set(aadhaars):
        text = text.replace(aadhaar, replace("AADHAAR", aadhaar))

    # Salary/compensation amounts (Indian format)
    salaries = re.findall(
        r'(?:Rs\.?|INR|₹)\s?[\d,]+(?:\.\d{1,2})?(?:\s?(?:per\s(?:month|annum|year)|\s?p\.?a\.?|lakh|lakhs|crore))?',
        text,
        re.IGNORECASE
    )
    for salary in set(salaries):
        text = text.replace(salary, replace("SALARY_AMOUNT", salary))

    # Date of birth patterns
    dobs = re.findall(
        r'\b(?:0?[1-9]|[12][0-9]|3[01])[\\/\\-\\.](?:0?[1-9]|1[012])[\\/\\-\\.](?:19|20)\d{2}\b',
        text
    )
    for dob in set(dobs):
        text = text.replace(dob, replace("DATE_OF_BIRTH", dob))

    return text, mapping


def unmask_text(text: str, mapping: dict) -> str:
    """Restores original values from placeholder mapping if needed."""
    for placeholder, original in mapping.items():
        text = text.replace(placeholder, original)
    return text


def analyze_contract_text(
    text: str,
    model_name: str = 'gemini-2.0-flash',
    mask_pii: bool = True,
) -> LegalAnalysisResult:
    """
    Analyzes legal contract text using Gemini models with structured Pydantic schema.
    Returns a full LegalAnalysisResult with clause-by-clause scoring, red flags, and negotiation points.
    """
    if not text.strip():
        raise ValueError("Contract text is empty.")
        
    client = get_client()
    if mask_pii:
        text_to_analyze, pii_mapping = mask_sensitive_info(text)
    else:
        text_to_analyze, pii_mapping = text, {}
    
    prompt = f"Please analyze the following contract text:\n\n---\n\n{text_to_analyze}\n\n---"
    
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={
            'system_instruction': SYSTEM_PROMPT,
            'response_mime_type': 'application/json',
            'response_schema': LegalAnalysisResult,
        }
    )
    
    if response.parsed is None:
        raise ValueError("Gemini did not return a valid structured contract analysis. Please try again.")

    analyze_contract_text.last_masked_text = text_to_analyze
    analyze_contract_text.last_pii_mapping = pii_mapping
    return response.parsed


# ---------------------------------------------------------------------------
# Contract Health Score (computed locally, not from Gemini)
# ---------------------------------------------------------------------------

def compute_health_score(result: LegalAnalysisResult) -> dict:
    """
    Compute a numeric Contract Health Score (0–100) from clause risk levels.

    Formula:
      - Start at 100
      - Each "low" risk clause:    −2
      - Each "medium" risk clause: −8
      - Each "high" risk clause:   −20
      - Clamped to [0, 100]

    Returns a dict with: score, label, color, interpretation.
    """
    DEDUCTIONS = {"low": 2, "medium": 8, "high": 20, "critical": 35}

    score = 100
    for clause in result.clauses:
        level = clause.risk_level.strip().lower()
        score -= DEDUCTIONS.get(level, 0)

    score = max(0, min(100, score))

    # Map to label + color + interpretation
    if score >= 80:
        label = "Low Risk"
        color = "#10b981"  # green
        interpretation = "This contract looks largely fair. A quick skim of flagged clauses should be enough."
    elif score >= 50:
        label = "Moderate Risk"
        color = "#f59e0b"  # amber / orange
        interpretation = "This contract has several clauses worth reviewing carefully before signing."
    else:
        label = "High Risk"
        color = "#ef4444"  # red
        interpretation = "This contract contains significant risks. Consider consulting a lawyer before signing."

    return {
        "score": score,
        "label": label,
        "color": color,
        "interpretation": interpretation,
    }


# ---------------------------------------------------------------------------
# Report Generation (Markdown & HTML)
# ---------------------------------------------------------------------------

def generate_markdown_report(result: LegalAnalysisResult) -> str:
    """Generate a downloadable Markdown report from the analysis result."""
    lines = []
    lines.append("# ⚖️ PocketLawAI — Contract Analysis Report\n")
    lines.append("> ⚠️ **Disclaimer:** PocketLawAI is an AI-assisted understanding tool. "
                 "It does NOT provide legal advice. For binding legal opinions, consult a licensed advocate.\n")
    
    # Overall Risk
    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "🚨"}.get(result.overall_risk_score.lower(), "⚪")
    lines.append(f"## 📊 Overall Risk: {risk_emoji} {result.overall_risk_score}\n")
    lines.append(f"{result.overall_risk_explanation}\n")
    
    # Summary
    lines.append("## 📝 Plain-English Summary\n")
    lines.append(f"{result.summary}\n")
    
    # Red Flags
    if result.red_flags:
        lines.append(f"## 🚩 Red Flags ({len(result.red_flags)})\n")
        for rf in result.red_flags:
            sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rf.severity.lower(), "⚪")
            lines.append(f"### {sev_emoji} {rf.pattern_name}\n")
            lines.append(f"- **Clause:** {rf.clause_reference}")
            lines.append(f"- **Severity:** {rf.severity}")
            lines.append(f"- **Why:** {rf.explanation}\n")
    
    # Hidden Penalties
    if result.hidden_penalties:
        lines.append(f"## 💰 Hidden Penalties ({len(result.hidden_penalties)})\n")
        for hp in result.hidden_penalties:
            sev_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(hp.severity.lower(), "⚪")
            lines.append(f"### {sev_emoji} {hp.penalty_title}\n")
            lines.append(f"> *\"{hp.penalty_text.strip()}\"*\n")
            lines.append(f"- **Impact:** {hp.implication}")
            lines.append(f"- **Mitigation:** {hp.mitigation}\n")
    
    # Clause-by-Clause
    lines.append("## 📋 Clause-by-Clause Breakdown\n")
    for c in result.clauses:
        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(c.risk_level.lower(), "⚪")
        flag_badge = " 🚩" if c.is_red_flag else ""
        lines.append(f"### Clause {c.clause_number}: {c.clause_title} — {risk_emoji} {c.risk_level}{flag_badge}\n")
        lines.append(f"> *\"{c.clause_text.strip()}\"*\n")
        lines.append(f"- **Risk reason:** {c.risk_reason}")
        if c.is_red_flag and c.red_flag_type:
            lines.append(f"- **Red flag:** {c.red_flag_type}")
        if c.negotiation_suggestion:
            lines.append(f"- **💡 Negotiation tip:** {c.negotiation_suggestion}")
        lines.append("")
    
    # Negotiation Points
    if result.negotiation_points:
        lines.append("## 🤝 Top Negotiation Points\n")
        for np_ in result.negotiation_points:
            lines.append(f"**{np_.priority}.** {np_.point}")
            lines.append(f"   - *Related to:* {np_.related_clause}")
            lines.append(f"   - *Why it matters:* {np_.rationale}\n")
    
    # Governing Law
    lines.append("## ⚖️ Governing Law & Jurisdiction\n")
    lines.append(f"{result.governing_law_notes}\n")
    
    # Footer disclaimer
    lines.append("---\n")
    lines.append("> ⚠️ **Disclaimer:** This report is generated by PocketLawAI, an AI tool. "
                 "It is NOT legal advice. Always consult a qualified lawyer before making legal decisions.\n")
    
    return "\n".join(lines)


def generate_html_report(result: LegalAnalysisResult) -> str:
    """Generate a styled, printable HTML report from the analysis result."""
    md_content = html_lib.escape(generate_markdown_report(result), quote=False)
    
    if MARKDOWN_AVAILABLE:
        body_html = md_lib.markdown(
            md_content,
            extensions=["tables", "fenced_code"]
        )
    else:
        # Fallback: wrap in pre if markdown library not available
        body_html = (
            f'<pre style="white-space: pre-wrap; font-family: inherit; '
            f'font-size: 0.95rem;">{md_content}</pre>'
        )
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PocketLawAI — Contract Analysis Report</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.7;
            color: #1a1a2e;
            background: #f8f9fc;
            padding: 2rem;
            max-width: 900px;
            margin: 0 auto;
        }}
        
        h1 {{
            background: linear-gradient(135deg, #1e3a5f 0%, #3b82f6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }}
        
        h2 {{
            color: #1e3a5f;
            font-size: 1.3rem;
            margin-top: 2rem;
            margin-bottom: 0.75rem;
            padding-bottom: 0.4rem;
            border-bottom: 2px solid #e2e8f0;
        }}
        
        h3 {{
            color: #334155;
            font-size: 1.05rem;
            margin-top: 1.2rem;
            margin-bottom: 0.4rem;
        }}
        
        blockquote {{
            border-left: 4px solid #3b82f6;
            background: #eff6ff;
            padding: 0.8rem 1rem;
            margin: 0.8rem 0;
            border-radius: 0 8px 8px 0;
            font-style: italic;
            color: #475569;
        }}
        
        ul, ol {{
            padding-left: 1.5rem;
            margin: 0.5rem 0;
        }}
        
        li {{
            margin: 0.3rem 0;
        }}
        
        strong {{
            color: #1e293b;
        }}
        
        .disclaimer {{
            background: #fef3c7;
            border: 1px solid #f59e0b;
            border-radius: 8px;
            padding: 1rem;
            margin: 1rem 0;
            font-size: 0.9rem;
        }}
        
        hr {{
            border: none;
            border-top: 1px solid #e2e8f0;
            margin: 2rem 0;
        }}
        
        @media print {{
            body {{ padding: 1rem; background: white; }}
            h1 {{ -webkit-text-fill-color: #1e3a5f; }}
        }}
    </style>
</head>
<body>
    <div class="disclaimer">
        ⚠️ <strong>Disclaimer:</strong> PocketLawAI is an AI-assisted understanding tool. 
        It does NOT provide legal advice. For binding legal opinions, consult a licensed advocate.
    </div>
    {body_html}
    <div class="disclaimer">
        ⚠️ <strong>Disclaimer:</strong> This report is generated by PocketLawAI, an AI tool.
        It is NOT legal advice. Always consult a qualified lawyer before making legal decisions.
    </div>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Contract Q&A — Ask questions about the contract
# ---------------------------------------------------------------------------

QA_SYSTEM_PROMPT = """\
You are a helpful legal assistant. The user has uploaded a contract \
and you have already analyzed it. Answer the user's question using \
ONLY the content of the contract provided below.

Do NOT give general legal advice. Only refer to what this specific \
contract says. If the contract does not address the question, say so \
clearly: "This contract doesn't mention that — you may want to ask \
the other party to clarify."

Keep your answer in plain English, under 100 words. No legal jargon.\
"""


def ask_contract_question(
    question: str,
    contract_text: str,
    analysis_json: str,
    model_name: str = "gemini-2.0-flash",
) -> str:
    """
    Answer a user's plain-English question about a specific contract.
    Uses the contract text + previously generated analysis as context.
    Returns a plain-English answer string.
    """
    if not question.strip():
        return "Please type a question first."

    client = get_client()

    prompt = (
        f"Contract text:\n\n{contract_text}\n\n"
        f"Previously identified clauses and risks:\n{analysis_json}\n\n"
        f"User's question: {question}"
    )

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={
            "system_instruction": QA_SYSTEM_PROMPT,
        },
    )

    return response.text


# ---------------------------------------------------------------------------
# Auto-Draft Counter-Clause
# ---------------------------------------------------------------------------

def draft_counter_clause(
    clause_text: str,
    risk_level: str,
    risk_reason: str,
    model_name: str = "gemini-2.0-flash",
) -> str:
    """
    Generate a fairer, rewritten version of a risky contract clause.
    Returns only the rewritten clause text (no preamble or labels).
    """
    client = get_client()

    prompt = (
        f"The following clause is from an Indian legal contract and has been "
        f"flagged as {risk_level} risk for the following reason: {risk_reason}\n\n"
        f"Original clause:\n{clause_text}\n\n"
        "Rewrite this clause to be fairer and more balanced for both parties, "
        "while keeping it legally valid under Indian law. The rewritten clause "
        "should:\n"
        "- Remove or limit the unfair element identified\n"
        "- Use plain, clear language (not complex legalese)\n"
        "- Be something a regular person could reasonably ask the other party "
        "to accept\n"
        "- Be concise — ideally 2–4 sentences\n\n"
        "Return ONLY the rewritten clause text, nothing else. No preamble, "
        "no explanation, no labels."
    )

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )

    return response.text.strip()


# ---------------------------------------------------------------------------
# AI Negotiation Simulator
# ---------------------------------------------------------------------------

def negotiate_clause(
    clause_text: str,
    risk_reason: str,
    contract_type: str,
    model_name: str = "gemini-2.0-flash",
) -> dict:
    """
    Generates a 3-turn negotiation script for a risky clause.
    Returns a dict with your_ask, company_response, your_counter.
    """
    client = get_client()

    prompt = f"""
You are an expert Indian contract negotiation coach.

A user is unhappy with this clause from a {contract_type} agreement:

CLAUSE:
{clause_text}

WHY IT'S RISKY:
{risk_reason}

Generate a realistic 3-turn negotiation script the user can
actually use. Return ONLY valid JSON, no markdown, no preamble:

{{
  "your_ask": {{
    "title": "What you should ask for",
    "script": "Exact words the user can say or write to the other party",
    "key_point": "One-line summary of the ask"
  }},
  "company_response": {{
    "title": "Likely company response",
    "script": "What the other party will probably say back",
    "key_point": "What they're really protecting"
  }},
  "your_counter": {{
    "title": "Your counter-offer",
    "script": "Exact words for a reasonable middle-ground counter",
    "key_point": "Why this counter is fair to both sides"
  }},
  "bottom_line": "One sentence: what's the minimum acceptable outcome for the user"
}}

Keep all scripts realistic, polite, and practical for Indian
workplace/rental context. No legal jargon in the scripts.
"""

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )

    text = response.text.strip() if response.text else ""
    text = text.replace("```json", "").replace("```", "").strip()
    if not text:
        raise ValueError("Gemini returned an empty negotiation script.")
    return json.loads(text)


# ---------------------------------------------------------------------------
# Share Text (WhatsApp / plain text)
# ---------------------------------------------------------------------------

def generate_share_text(result: LegalAnalysisResult, health: dict) -> str:
    """
    Generate a clean plain-text summary for sharing (WhatsApp, clipboard, etc.).
    `health` is the dict returned by compute_health_score().
    """
    lines = []
    lines.append("🔍 PocketLawAI Contract Analysis\n")

    # Health score
    lines.append(f"📊 Contract Health Score: {health['score']}/100 — {health['label']}\n")

    # Key terms
    if hasattr(result, 'key_terms') and result.key_terms:
        lines.append("📋 Key Terms:")
        for kt in result.key_terms[:8]:
            lines.append(f"- {kt.label}: {kt.value}")
        lines.append("")

    # Red flags
    lines.append(f"🚨 Red Flags Found: {len(result.red_flags)}")
    for rf in result.red_flags:
        lines.append(f"• {rf.pattern_name}: {rf.explanation[:80]}")
    lines.append("")

    # High risk clauses
    high_clauses = [c for c in result.clauses if c.risk_level.lower() == "high"]
    if high_clauses:
        lines.append("⚠️ Top Risk Clauses:")
        for c in high_clauses:
            lines.append(f"• Clause {c.clause_number} ({c.clause_title}): {c.risk_reason}")
        lines.append("")

    lines.append("✅ Analyzed by PocketLawAI — AI-powered Indian contract analyzer")
    lines.append("Note: This is an AI-assisted summary, not legal advice.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PDF Report (fpdf2)
# ---------------------------------------------------------------------------

def generate_pdf_report(result: LegalAnalysisResult, health: dict) -> bytes:
    """
    Generate a styled PDF report using fpdf2.
    Returns the PDF as bytes for download.
    `health` is the dict returned by compute_health_score().
    """
    from fpdf import FPDF
    from datetime import date

    class PocketLawPDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 18)
            self.set_text_color(30, 58, 95)
            self.cell(0, 12, "PocketLawAI", new_x="LMARGIN", new_y="NEXT", align="L")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(100, 116, 139)
            self.cell(0, 5, "AI-Powered Contract Analysis Report", new_x="LMARGIN", new_y="NEXT", align="L")
            self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
            self.ln(6)

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(148, 163, 184)
            self.cell(0, 10, "Generated by PocketLawAI | This is not legal advice", align="C")
            self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="R")

    pdf = PocketLawPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ─── Page 1 ───
    pdf.add_page()

    # Date
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 6, f"Date: {date.today().strftime('%d %B %Y')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Health Score
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, "Contract Health Score", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 28)
    score_color = (16, 185, 129) if health["score"] >= 80 else (245, 158, 11) if health["score"] >= 50 else (239, 68, 68)
    pdf.set_text_color(*score_color)
    pdf.cell(0, 16, _safe_text(f"{health['score']} / 100  --  {health['label']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(71, 85, 105)
    pdf.cell(0, 6, _safe_text(health["interpretation"]), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Summary
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, "Plain-English Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(51, 65, 85)
    try:
        pdf.multi_cell(0, 5.5, _safe_text(result.summary))
    except Exception:
        pdf.multi_cell(0, 5.5, "[Content could not be rendered]")
    pdf.ln(4)

    # Key Terms table
    if hasattr(result, 'key_terms') and result.key_terms:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 8, "Key Terms", new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(241, 245, 249)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(60, 7, "Term", border=1, fill=True)
        pdf.cell(0, 7, "Value", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(51, 65, 85)
        for kt in result.key_terms[:8]:
            try:
                pdf.cell(60, 7, _safe_text(kt.label), border=1)
                pdf.cell(0, 7, _safe_text(kt.value), border=1, new_x="LMARGIN", new_y="NEXT")
            except Exception:
                pdf.cell(60, 7, "[Error]", border=1)
                pdf.cell(0, 7, "[Content could not be rendered]", border=1, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # ─── Page 2 ───
    pdf.add_page()

    # Red Flags
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(239, 68, 68)
    pdf.cell(0, 8, f"Red Flags ({len(result.red_flags)})", new_x="LMARGIN", new_y="NEXT")
    if result.red_flags:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(51, 65, 85)
        for rf in result.red_flags:
            try:
                pdf.multi_cell(0, 5, _safe_text(f"* {rf.pattern_name} ({rf.severity}): {rf.explanation}"))
            except Exception:
                pdf.multi_cell(0, 5, "[Content could not be rendered]")
            pdf.ln(1)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 6, "No red flags detected.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # High Risk Clauses
    high_clauses = [c for c in result.clauses if c.risk_level.lower() == "high"]
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(239, 68, 68)
    pdf.cell(0, 8, f"High Risk Clauses ({len(high_clauses)})", new_x="LMARGIN", new_y="NEXT")
    if high_clauses:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(51, 65, 85)
        for c in high_clauses:
            try:
                pdf.multi_cell(0, 5, _safe_text(f"* Clause {c.clause_number} - {c.clause_title}: {c.risk_reason}"))
            except Exception:
                pdf.multi_cell(0, 5, "[Content could not be rendered]")
            pdf.ln(1)
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 6, "No high-risk clauses found.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Negotiation Suggestions
    if result.negotiation_points:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(59, 130, 246)
        pdf.cell(0, 8, "Negotiation Suggestions", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(51, 65, 85)
        for np_ in result.negotiation_points:
            try:
                pdf.multi_cell(0, 5, _safe_text(f"{np_.priority}. {np_.point} (Re: {np_.related_clause})"))
            except Exception:
                pdf.multi_cell(0, 5, "[Content could not be rendered]")
            pdf.ln(1)

    return bytes(pdf.output())


def _safe_text(text: str) -> str:
    """Sanitize text for fpdf2 Latin-1 fonts (Helvetica)."""
    if not text:
        return ""
    replacements = {
        "\u2018": "'", "\u2019": "'",   # curly single quotes
        "\u201c": '"', "\u201d": '"',   # curly double quotes
        "\u2013": "-",                   # en dash
        "\u2014": "--",                  # em dash
        "\u2026": "...",                 # ellipsis
        "\u20b9": "INR ",               # ₹ rupee sign
        "\u2022": "*",                   # bullet
        "\u00a0": " ",                   # non-breaking space
        "\u2010": "-",                   # hyphen
        "\u2011": "-",                   # non-breaking hyphen
        "\u2012": "-",                   # figure dash
        "\u2015": "--",                  # horizontal bar
        "\u00b7": "*",                   # middle dot
        "\u25cf": "*",                   # black circle
        "\u2192": "->",                  # right arrow
        "\u2190": "<-",                  # left arrow
        "\u00e9": "e",                   # é
        "\u00e0": "a",                   # à
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Final safety net: strip anything outside Latin-1
    return text.encode("latin-1", errors="replace").decode("latin-1")


# ---------------------------------------------------------------------------
# Worst-Case Scenario Generator
# ---------------------------------------------------------------------------

def generate_worst_case(
    contract_text: str,
    analysis: LegalAnalysisResult,
    model_name: str = "gemini-2.0-flash",
) -> dict:
    """
    Generates plain-English worst-case consequences
    if the user signs the contract as-is.

    Args:
        contract_text: The full contract text.
        analysis: The LegalAnalysisResult from a prior analysis.
        model_name: Gemini model to use.

    Returns:
        A dict with keys: consequences (list), bottom_line (str),
        recommendation (str).
    """
    client = get_client()

    # Collect high-risk clauses from the structured result
    high_risk_clauses = []
    for c in analysis.clauses:
        if c.risk_level.strip().lower() == "high":
            high_risk_clauses.append({
                "clause_number": c.clause_number,
                "clause_title": c.clause_title,
                "clause_text": c.clause_text,
                "risk_reason": c.risk_reason,
                "red_flag_type": c.red_flag_type,
            })

    prompt = f"""
You are an honest Indian legal advisor. A person is about to sign \
a contract. Based on the risky clauses, tell them in plain Hindi-\
English what the WORST realistic outcomes are if they sign today.

HIGH RISK CLAUSES FOUND:
{json.dumps(high_risk_clauses, indent=2)}

FULL CONTRACT SUMMARY:
{contract_text[:2000]}

Return ONLY valid JSON, no markdown, no preamble:

{{
  "consequences": [
    {{
      "headline": "Short punchy headline of the consequence",
      "plain_explanation": "1-2 sentences in simple English explaining \
exactly what could happen to the person. Real world, not legal language.",
      "clause_reference": "Which clause causes this",
      "severity": "high/medium/low"
    }}
  ],
  "bottom_line": "One honest sentence summarizing the overall risk \
of signing this contract right now.",
  "recommendation": "One actionable thing the person should do \
before signing — be specific."
}}

Rules:
- Maximum 5 consequences
- Write like you're warning a friend, not writing a legal brief
- Only include REALISTIC worst cases, not hypothetical edge cases
- Focus on consequences specific to Indian employment/rental law context
- Order by severity — highest risk first
"""

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )

    text = response.text.strip() if response.text else ""
    text = text.replace("```json", "").replace("```", "").strip()
    if not text:
        raise ValueError("Gemini returned an empty worst-case analysis.")
    return json.loads(text)
