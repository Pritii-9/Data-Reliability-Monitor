# 🛡️ Data Reliability Control Center

A decoupled application designed for automated data pipeline monitoring, real-time quality validation, AI-powered Root Cause Analysis (RCA), and incident queue management. Built to demonstrate core **Data Engineering**, **Data Observability (SLA/MTTR)**, and **Production Support Architecture**.

---

## 🏗️ Decoupled Architecture

```text
               +-------------------------------------------------------+
               |                  Local Data Storage                   |
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
   |   - Deep Multi-Field Audit Search Engine (File, ID, Check, Details)           |
   |   - Direct SQL Rollbacks & Confirmation Popovers                              |
   +-------------------------------------------------------------------------------+
```

---

## 🛠️ Key Capabilities & Features

* **⚡ Decoupled Backend API**: FastAPI engine handling file ingestion, validation rule evaluation, and RCA payload generation.
* **🤖 Automated AI Root Cause Analysis (RCA)**: Integrated LLM engine supporting **Google AI Studio API Key (`GEMINI_API_KEY`)**, Gemini models, OpenAI fallback, and an intelligent rule-based heuristic engine for instant troubleshooting.
* **🛡️ Data Observability & SLA Tracking**: Monitoring of pass-rate compliance, pipeline latency, and Mean Time to Resolution (MTTR).
* **🔍 Deep Multi-Field Audit Search**: Multi-field search across execution IDs, file names, check names, and error details.

---

## 💻 Tech Stack

* **Backend API**: Python 3.11+, FastAPI, Uvicorn, Pydantic
* **Observability UI**: Streamlit, Altair
* **Storage & DB**: Local Storage, SQLAlchemy, SQLite (Default) / PostgreSQL
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
uvicorn src.api.app:app --reload --port 8000
```

### 4. Run Streamlit Control Center
```bash
streamlit run dashboard.py
```

### 5. Execute Test Suite
```bash
python -m pytest tests/
```
