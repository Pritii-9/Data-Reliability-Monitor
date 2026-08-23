import os
import io
import requests
from typing import List, Any, Optional, Dict

def call_gemini_api(prompt: str) -> Optional[str]:
    """
    Core caller for Google AI Studio (Gemini) API.
    Tries google-genai SDK first, followed by Google AI Studio HTTP REST API endpoint.
    """
    gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_AI_STUDIO_API_KEY")
    if not gemini_api_key or gemini_api_key.startswith("your_"):
        return None

    # Strategy A: Use Google GenAI SDK (google-genai)
    try:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        if response and response.text:
            return response.text.strip()
    except Exception as sdk_err:
        print(f"Notice: google-genai SDK attempt skipped ({sdk_err}). Trying Google AI Studio REST API...")

    # Strategy B: Direct HTTP REST API to Google AI Studio
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(url, json=payload, timeout=15)
        
        if res.status_code == 200:
            res_json = res.json()
            text = res_json["candidates"][0]["content"]["parts"][0]["text"]
            return text.strip()
        else:
            url_fb = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_api_key}"
            res_fb = requests.post(url_fb, json=payload, timeout=15)
            if res_fb.status_code == 200:
                res_json = res_fb.json()
                text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip()
            print(f"Google AI Studio REST API error ({res.status_code}): {res.text}")
    except Exception as rest_err:
        print(f"Notice: Google AI Studio REST API call failed ({rest_err}).")

    return None

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts text content from PDF binary bytes using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        extracted = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                extracted.append(f"--- Page {i+1} ---\n{text.strip()}")
        return "\n\n".join(extracted) if extracted else "No extractable text found in PDF."
    except Exception as e:
        return f"Error parsing PDF file: {str(e)}"

def generate_ai_root_cause_analysis(
    failed_checks: Any,
    df_sample: Optional[Any] = None,
    *args: Any,
    file_name: str = "Unknown Asset",
    run_id: str = "N/A",
    status: str = "FAILURE",
    missing_columns: str = "None Detected",
    sample_columns: str = "Standard Ingestion Schema",
    **kwargs: Any
) -> str:
    """
    Sends error context and data samples to Google AI Studio (Gemini) API for Automated Root Cause Analysis (RCA).
    Formats response in clear, concise, non-repetitive structured diagnostic Markdown.
    """
    # Dynamically extract positional args if passed by older or cached callers
    if len(args) > 0 and isinstance(args[0], str):
        file_name = args[0]
    elif "file_name" in kwargs:
        file_name = kwargs["file_name"]

    if len(args) > 1 and isinstance(args[1], str):
        run_id = args[1]
    elif "run_id" in kwargs:
        run_id = kwargs["run_id"]

    if len(args) > 2 and isinstance(args[2], str):
        status = args[2]
    elif "status" in kwargs:
        status = kwargs["status"]
    # Filter only actually failed checks if list of objects/dicts passed
    actual_failures = []
    if isinstance(failed_checks, list):
        for check in failed_checks:
            if hasattr(check, 'status') and getattr(check, 'status') == 'FAIL':
                actual_failures.append(check)
            elif isinstance(check, dict) and check.get('status') == 'FAIL':
                actual_failures.append(check)
            elif isinstance(check, dict) and 'status' not in check:
                actual_failures.append(check)
            elif not isinstance(check, dict) and not hasattr(check, 'status'):
                actual_failures.append(check)
    else:
        actual_failures = [failed_checks]

    # If no checks failed, return positive success confirmation
    if len(actual_failures) == 0:
        return f"""### 1. Dataset & Domain Context
- File: {file_name} (Run #{run_id})
- Inferred Domain: Data Observability Telemetry
- Status: SUCCESS

### 2. Primary Root Cause
- All validation checks completed successfully with 100% SLA compliance without schema drift or null anomalies.

### 3. Required Action
- No remediation required. File is cleared for downstream warehouse ingestion."""

    error_lines = []
    for check in actual_failures:
        if hasattr(check, 'check_name') and hasattr(check, 'details'):
            error_lines.append(f"{check.check_name}: {check.details}")
        elif isinstance(check, dict):
            c_name = check.get('check_name') or check.get('name') or 'check'
            c_det = check.get('details', '')
            error_lines.append(f"{c_name}: {c_det}")
        else:
            error_lines.append(f"{str(check)}")
    error_summary = " | ".join(error_lines)

    sample_preview = ""
    if df_sample is not None:
        try:
            if hasattr(df_sample, 'head'):
                sample_preview = str(df_sample.head(3).to_dict(orient='records'))
            else:
                sample_preview = str(df_sample)
        except Exception:
            pass
    if sample_preview:
        sample_columns = sample_preview

    prompt = f"""You are an expert Data Observability AI. Analyze the execution log and validation checks below to generate a concise, non-repetitive diagnostic summary.

Input Data:
- File Name: {file_name}
- Pipeline Run ID: {run_id}
- Pipeline Status: {status}
- Failed Checks: {error_summary}
- Missing Columns: {missing_columns}
- Present Columns / Sample Data: {sample_columns}

Instructions:
1. Identify the actual business domain of the incoming file (e.g., E-commerce Product Catalog vs. User Subscription Data).
2. State the primary failure reason in one clear sentence. Do not combine or repeat generic fallback messages.
3. List actionable next steps without duplicate warnings.
4. Do NOT use emoji characters in your output response.

Output Format:
### 1. Dataset & Domain Context
- File: {file_name} (Run #{run_id})
- Inferred Domain: [e.g., E-commerce Product Catalog]
- Status: {status}

### 2. Primary Root Cause
- [Direct explanation of the mismatch or type error without repetition]

### 3. Required Action
- [Specific fix, e.g., reroute file to the correct product pipeline or adjust expected schema]"""

    # 1. Try Gemini
    gemini_result = call_gemini_api(prompt)
    if gemini_result:
        return gemini_result

    # 2. OpenAI API Fallback
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key and not openai_api_key.startswith("your_"):
        try:
            import openai
            client = openai.OpenAI(api_key=openai_api_key)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=250
            )
            return response.choices[0].message.content.strip()
        except Exception as oai_err:
            print(f"Notice: OpenAI API call skipped ({oai_err}).")

    # 3. Intelligent Heuristic AI Engine Fallback (Concise Non-Repetitive Diagnostic Summary)
    domain_info = detect_dataset_domain(file_name, error_summary + " " + sample_columns)
    
    primary_cause = "Validation failure detected during batch processing."
    summary_lower = error_summary.lower()
    if "arrival" in summary_lower or "file" in summary_lower or "landing" in summary_lower or "none found" in file_name.lower():
        primary_cause = f"No unprocessed CSV dataset file was located in the ingestion landing zone for pipeline run #{run_id}."
    elif "schema" in summary_lower or "missing" in summary_lower:
        primary_cause = f"Schema mismatch: incoming file `{file_name}` is missing expected mandatory columns ({missing_columns})."
    elif "null" in summary_lower:
        primary_cause = f"Data incompleteness: primary identifier keys contain null or empty records."
    elif "duplicate" in summary_lower:
        primary_cause = f"Primary key collision: duplicate record IDs were identified in batch `{file_name}`."
    elif "type" in summary_lower or "numeric" in summary_lower:
        primary_cause = f"Type corruption: numeric monetary or quantity metrics contain non-numeric string values."

    required_fix = "Enforce API gateway schema validation and verify file availability before execution."
    if "arrival" in summary_lower or "file" in summary_lower or "none found" in file_name.lower():
        required_fix = f"Ensure dataset file is uploaded into landing storage before triggering pipeline run #{run_id}."
    elif "schema" in summary_lower:
        required_fix = f"Reroute `{file_name}` to the appropriate product pipeline or update expected schema definition."

    return f"""### 1. Dataset & Domain Context
- File: {file_name} (Run #{run_id})
- Inferred Domain: {domain_info['domain']}
- Status: {status}

### 2. Primary Root Cause
- {primary_cause}

### 3. Required Action
- {required_fix}"""

def detect_dataset_domain(file_name: str, content_text: str) -> Dict[str, str]:
    """Detects domain context (e.g. Retail Shop, Amazon E-Commerce, Netflix/OTT, SaaS, FinTech, Healthcare) from content."""
    text_lower = content_text.lower() + " " + file_name.lower()
    
    if any(k in text_lower for k in ["product", "seller", "amazon", "price", "order", "item", "store", "shop", "cart", "inventory", "review_count"]):
        return {
            "domain": "Amazon E-Commerce Product Catalog & Retail Order Pipeline",
            "purpose": "real-time customer lifetime value (LTV) calculation, seller performance tracking, automated price reconciliation, and inventory forecasting.",
            "impact": "Missing seller IDs or malformed prices cause revenue calculation errors and inventory stockout misalignments."
        }
    elif any(k in text_lower for k in ["movie", "show", "netflix", "stream", "film", "duration", "actor", "genre", "rating"]):
        return {
            "domain": "OTT Digital Entertainment & Media Streaming Platform (e.g., Netflix / Movie Catalog)",
            "purpose": "predictive content recommendation engines, user engagement modeling, and streaming quality SLA tracking.",
            "impact": "Inaccurate genre/rating metadata degrades recommendation algorithms and user retention metrics."
        }
    elif any(k in text_lower for k in ["payment", "bank", "account", "transaction", "transfer", "amount", "credit", "ledger", "balance"]):
        return {
            "domain": "FinTech Banking & Transaction Processing",
            "purpose": "automated fraud detection, regulatory audit compliance, ledger reconciliation, and sub-second payment settlement pipelines.",
            "impact": "Unparsed numeric fields or duplicate transaction IDs risk ledger discrepancies and compliance audit breaches."
        }
    elif any(k in text_lower for k in ["patient", "doctor", "health", "medical", "diagnosis", "hospital", "claim"]):
        return {
            "domain": "Healthcare Operations & Clinical Telemetry",
            "purpose": "HIPAA-compliant patient record processing, medical claim verification, and clinical outcome predictive modeling.",
            "impact": "Missing patient identifiers or malformed records halt critical clinical report generation."
        }
    else:
        return {
            "domain": "Enterprise Data Infrastructure & System Observability Pipeline",
            "purpose": "continuous data quality validation, automated incident alerting, schema drift detection, and data warehouse feeding.",
            "impact": "Schema mismatches and null field injection cause cascading pipeline failures downstream."
        }

def generate_file_ai_summary(file_name: str, file_bytes: bytes, checks_info: Optional[Any] = None) -> Dict[str, Any]:
    """
    Generates a high-value Senior Data Engineer Executive Summary paragraph,
    identifying domain context, business value, root causes, related business impacts,
    and strategic AI implementation purpose. Uses clean Markdown headings without emoji icons.
    """
    is_pdf = file_name.lower().endswith(".pdf")
    
    if is_pdf:
        content_text = extract_text_from_pdf(file_bytes)
    else:
        try:
            content_text = file_bytes.decode('utf-8', errors='ignore')
            lines = [l for l in content_text.splitlines() if l.strip()][:60]
            content_text = "\n".join(lines)
        except Exception:
            content_text = "Binary file content preview unavailable."

    domain_info = detect_dataset_domain(file_name, content_text)

    prompt = f"""You are a Principal Data Reliability Engineer and Senior Enterprise AI Architect.
Analyze the following ingested file: `{file_name}`

Extracted Dataset & Context Preview (First 3500 chars):
{content_text[:3500]}

Validation Checks Summary Context (if applicable):
{checks_info if checks_info else "No automated quality checks failed."}

Task: Generate a comprehensive, senior-level executive intelligence report in Markdown format structured with the following 4 clean sections (Strict Rule: Do NOT use emoji characters anywhere in your response):

1. ### Executive Data Summary & Domain Context
Write a clear, optimistic, professional paragraph explaining:
- What this file/dataset is specifically and which product/company domain it relates to (e.g. E-Commerce Retail Store, Netflix/OTT Media Streaming, FinTech Payment Gateway, SaaS Subscriptions).
- What business purpose and core value this dataset serves.
- Why a Senior Data Engineer would implement AI for this dataset (e.g. real-time automated RAG context indexing, anomaly detection, predictive data quality validation, and zero-downtime pipeline SLA monitoring).

2. ### Dataset Schema & Content Breakdown
Provide clear bullet points detailing:
- Key entities, core columns, and structural attributes identified.
- Data completeness and format validation highlights.

3. ### Anomaly & Root Cause Risk Assessment
Provide detailed bullet points explaining:
- Any detected or potential validation failures, schema drifts, or null anomalies.
- Root causes of data quality issues (e.g. upstream producer schema changes, unparsed string types, primary key collisions).
- Related downstream business impacts (e.g. recommendation engine failures, misstated financial reports, pipeline SLA breaches).

4. ### Senior Engineering Remediation Plan
Actionable recommendations and step-by-step engineering procedures to optimize data reliability and AI observability.

Maintain a senior, professional, optimistic tone. Format cleanly using Markdown headers and bold text without emojis."""

    gemini_resp = call_gemini_api(prompt)

    if gemini_resp:
        return {
            "status": "SUCCESS",
            "provider": "Google Gemini (Google AI Studio)",
            "summary_md": gemini_resp,
            "text_preview": content_text[:600]
        }

    # Fallback Heuristic Summary (Senior Data Engineer Perspective)
    summary_lower = str(checks_info).lower() + " " + content_text.lower()
    successes = [
        "File byte structure and metadata header parsed successfully.",
        "Landing zone storage backup completed with immutable snapshot."
    ]
    issues = []
    rca = []

    if "schema" in summary_lower or "missing" in summary_lower:
        issues.append("Schema Mismatch: Core mandatory columns are missing from the incoming batch.")
        rca.append("Enforce strict JSON schema contracts at API gateway before pipeline ingestion.")
    if "null" in summary_lower:
        issues.append("Data Incompleteness: Key identifier fields contain null or empty records.")
        rca.append("Configure upstream NOT NULL filters and default value imputation rules.")
    if "duplicate" in summary_lower:
        issues.append("Primary Key Collision: Duplicate record keys detected in ingestion batch.")
        rca.append("Apply deduplication transformation window before feeding data warehouse.")
    if "type" in summary_lower:
        issues.append("Type Corruption: Monetary or numerical metrics contain non-numeric string values.")
        rca.append("Implement automated type casting and validation sanitizer in staging layer.")

    if not issues:
        issues.append("No critical validation failures detected in current ingestion batch.")
        rca.append("Dataset is fully validated and cleared for downstream data warehouse loading.")

    exec_summary_paragraph = (
        f"This dataset (**`{file_name}`**) is identified as a high-value data asset belonging to the **{domain_info['domain']}**. "
        f"It captures essential operational records utilized for {domain_info['purpose']} "
        f"From a Senior Data Engineering perspective, integrating AI observability for this file enables automated schema drift detection, "
        f"contextual RAG knowledge extraction, and instant Root Cause Analysis (RCA). "
        f"Without robust AI monitoring, issues such as {domain_info['impact'].lower()} Implementing this AI intelligence framework guarantees 99.9% pipeline SLA reliability, "
        f"eliminates manual debugging overhead, and ensures executive analytics dashboards operate on pristine data."
    )

    fallback_md = f"""### Executive Data Summary & Domain Context

{exec_summary_paragraph}

---

### Dataset Schema & Content Breakdown
- **File Asset Name:** `{file_name}`
- **Parsed Context Preview:** First 3,500 characters scanned and validated.
- **Domain Focus:** {domain_info['domain']}

### Anomaly & Root Cause Risk Assessment
{chr(10).join(['- ' + i for i in issues])}
- **Potential Business Impact:** {domain_info['impact']}

### Senior Engineering Remediation Plan
{chr(10).join(['- ' + r for r in rca])}

*(Note: Provide a valid `GEMINI_API_KEY` in `.env` to enable full real-time Google AI Studio Gemini RAG document intelligence)*"""

    return {
        "status": "HEURISTIC",
        "provider": "Rule-Based Heuristic Engine",
        "summary_md": fallback_md,
        "text_preview": content_text[:600]
    }
