# 🛡️ Enterprise Data Reliability Control Center & Observability Engine

An enterprise-grade, decoupled microservice platform designed for automated data pipeline monitoring, real-time quality validation, AI-powered Root Cause Analysis (RCA), and incident queue management. Built to demonstrate core **Data Engineering**, **Data Observability (SLA/MTTR)**, and **Production Support Architecture**.

---

## 🏗️ Decoupled Microservice Architecture

```text
               +-------------------------------------------------------+
               |                  S3 / Cloud Storage                   |
               |             (Landing / Processed / Quarantine)        |
               +-------------------------------------------------------+
                                           |
                                           v
   +-------------------------------------------------------------------------------+
   |                             FastAPI Engine (Port 8000)                        |
   |   - REST Ingestion API (/analyze-upload)                                      |
   |   - Automated Validation: Schema Drift, Null Bounds, Row Count Anomalies     |
   |   - AI-Driven Root Cause Analysis (LLM / OpenAI + Fallback Heuristics)       |
   +-------------------------------------------------------------------------------+
                       |                                       |
                       v                                       v
         +--------------------------+             +--------------------------+
         |  PostgreSQL / SQLite DB  |             |  Incident Queue System   |
         |  (Runs, Check Results)   |             |  (Auto Ticket + Alerts)  |
         +--------------------------+             +--------------------------+
                       ^                                       ^
                       |                                       |
   +-------------------------------------------------------------------------------+
   |                            Streamlit Control Center                           |
   |   - Vector Icon Navigation (streamlit-option-menu & FontAwesome)              |
   |   - Deep Multi-Field Audit Search Engine (File, ID, Check, Details)           |
   |   - Sub-50ms Direct SQL Rollbacks & Confirmation Popovers                   |
   +-------------------------------------------------------------------------------+
```

---

## 🛠️ Key Capabilities & Features

* **⚡ Decoupled Backend Microservice**: High-throughput FastAPI API engine handling file ingestion, validation rule evaluation, and RCA payload generation.
* **🤖 Automated AI Root Cause Analysis (RCA)**: Integrated LLM engine supporting **Google AI Studio API Key (`GEMINI_API_KEY`)**, Gemini 2.5/1.5 Flash models, OpenAI fallback, and an intelligent rule-based heuristic engine for instant pipeline troubleshooting.
* **🛡️ Data Observability & SLA Tracking**: Real-time monitoring of pass-rate compliance, pipeline latency, and Mean Time to Resolution (MTTR).
* **🔍 Deep Multi-Field Audit Search**: Multi-field search across execution IDs, file names, cloud storage keys, check names, and error details.
* **📖 Production Runbooks**: SOP documentation for common pipeline incidents (`missing-file`, `schema-mismatch`, `null-values`, `low-row-count`).

---

## 💻 Tech Stack

* **Backend API**: Python 3.11+, FastAPI, Uvicorn, Pydantic
* **Observability UI**: Streamlit, `streamlit-option-menu`, FontAwesome 6, Altair
* **Storage & DB**: Supabase S3 Object Storage, SQLAlchemy, SQLite (Default) / PostgreSQL
* **Quality Engine**: Pandas, Automated Rule Validation Suite
* **Testing & CI**: Pytest, GitHub Actions

---

## 🚀 Getting Started

### 1. Environment Setup
Copy `.env.example` to `.env` and configure credentials:
```bash
cp .env.example .env
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run FastAPI Backend Engine
```bash
uvicorn api:app --reload --port 8000
```

### 4. Run Streamlit Control Center
```bash
streamlit run dashboard.py
```

### 5. Execute Test Suite
```bash
pytest tests/
```

---

## 📖 Operational SOP Runbooks

Detailed resolution protocols are available in the [`runbooks/`](./runbooks) directory:
* [`missing-file.md`](./runbooks/missing-file.md) - Handling missing batch drops & arrival delays
* [`schema-mismatch.md`](./runbooks/schema-mismatch.md) - Resolving column mutation and schema drift
* [`null-values.md`](./runbooks/null-values.md) - Inspecting null threshold breaches
* [`low-row-count.md`](./runbooks/low-row-count.md) - Investigating row volume anomalies
