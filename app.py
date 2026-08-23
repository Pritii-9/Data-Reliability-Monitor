import streamlit as st
import requests
import pandas as pd
import json

# Page Config
st.set_page_config(
    page_title="Data Reliability Control Center",
    page_icon="🤖",
    layout="wide"
)

# Custom Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .main-title { font-size: 32px; font-weight: 800; color: #818cf8; margin-bottom: 5px; }
    .sub-title { font-size: 14px; color: #94a3b8; margin-bottom: 25px; }
    .rca-box {
        background-color: #1e1b4b;
        border: 1px solid #6366f1;
        border-left: 5px solid #818cf8;
        padding: 18px;
        border-radius: 8px;
        margin-top: 15px;
        margin-bottom: 20px;
    }
    .status-pass { color: #4ade80; font-weight: bold; }
    .status-fail { color: #f87171; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="main-title">🤖 Data Reliability Control Center</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Decoupled Microservice Architecture &nbsp;|&nbsp; FastAPI Engine &nbsp;|&nbsp; Automated AI Root Cause Analysis</div>', unsafe_allow_html=True)

# FastAPI Endpoint Configuration
FASTAPI_ENDPOINT = "http://localhost:8000/analyze-upload"

# Sidebar Backend Health Check
with st.sidebar:
    st.markdown("### ⚙️ System Status")
    try:
        health_resp = requests.get("http://localhost:8000/", timeout=2)
        if health_resp.status_code == 200:
            st.success("🟢 FastAPI Backend: Connected")
        else:
            st.error("🔴 FastAPI Backend: Degraded")
    except Exception:
        st.warning("⚠️ FastAPI Backend: Offline (Start `uvicorn api:app --port 8000`)")
        
    st.markdown("---")
    st.markdown("### 📌 Architecture Summary")
    st.markdown("""
    - **Frontend:** Streamlit Microservice UI
    - **Backend:** FastAPI Async REST API (`port 8000`)
    - **AI Engine:** LLM Automated Root Cause Analysis
    - **Validation:** Type Check, Schema, Nulls, Duplicates
    """)

# Main File Upload Area
st.markdown("### 📤 Ingest & Analyze Dataset")
uploaded_file = st.file_uploader("Upload incoming CSV batch to validate through FastAPI pipeline", type=["csv"])

if uploaded_file is not None:
    st.markdown("---")
    st.markdown(f"**Selected File:** `{uploaded_file.name}` ({uploaded_file.size} bytes)")
    
    if st.button("🚀 Analyze Batch via FastAPI Backend", type="primary", use_container_width=True):
        with st.spinner("Transmitting dataset to FastAPI engine & running AI validations..."):
            try:
                # Prepare file for multipart/form-data POST request
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "text/csv")}
                response = requests.post(FASTAPI_ENDPOINT, files=files, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    st.markdown("## 📊 Analysis Results")
                    
                    # Top Metrics
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Pipeline Status", data['status'])
                    col2.metric("Total Rows", f"{data['total_rows']:,}")
                    col3.metric("Total Columns", data['total_columns'])
                    col4.metric("Destination Bucket", "processed/" if data['status'] == "SUCCESS" else "quarantine/")
                    
                    # AI Root Cause Analysis Section if Failure Detected
                    if data['status'] == "FAILURE" and data.get('root_cause_analysis'):
                        st.markdown("""
                        <div class="rca-box">
                            <h4 style="margin-top:0; color:#c084fc;">🧠 AI Automated Root Cause Analysis (RCA)</h4>
                            <p style="color:#e2e8f0; font-size:15px; margin-bottom:0;">""" + data['root_cause_analysis'] + """</p>
                        </div>
                        """, unsafe_allow_html=True)
                    elif data['status'] == "SUCCESS":
                        st.balloons()
                        st.success("🎉 Pipeline Ingestion Passed All Data Reliability Validations!")

                    # Detailed Checks Table
                    st.markdown("### 📋 Validation Checks Breakdown")
                    checks_df = pd.DataFrame(data['checks'])
                    
                    def highlight_status(val):
                        return 'color: #4ade80; font-weight: bold' if val == 'PASS' else 'color: #f87171; font-weight: bold'
                        
                    styled_df = checks_df.style.map(highlight_status, subset=['status'])
                    st.dataframe(styled_df, use_container_width=True, hide_index=True)
                    
                    # Raw API Response Viewer
                    with st.expander("🛠️ Inspect Raw FastAPI JSON Payload"):
                        st.json(data)
                        
                else:
                    st.error(f"Backend API returned error {response.status_code}: {response.text}")
                    
            except requests.exceptions.ConnectionError:
                st.error("🔌 Could not connect to FastAPI server. Please start the backend server at `http://localhost:8000`.")
            except Exception as e:
                st.error(f"Unexpected error during analysis: {e}")
