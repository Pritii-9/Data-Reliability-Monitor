import os
import streamlit as st
import pandas as pd
import requests
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from ticketing import resolve_ticket
from database import SessionLocal, PipelineRun, CheckResult
import altair as alt
from datetime import datetime
import subprocess
import sys
from supabase import create_client, Client
from streamlit_option_menu import option_menu

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Setup Database Connection
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./monitor.db")
engine = create_engine(DATABASE_URL)

@st.cache_data(ttl=15, show_spinner=False)
def check_fastapi_health():
    """Cache API health check for 15 seconds to prevent network lag on every UI click."""
    try:
        res = requests.get("http://localhost:8000/", timeout=0.5)
        return res.status_code == 200
    except Exception:
        return False

@st.cache_data(ttl=10, show_spinner=False)
def fetch_data(query):
    """Fetch data from the database with a 10-second cache to prevent DB locking/spam."""
    return pd.read_sql(query, engine)

def delete_pipeline_run(run_id, storage_location=None):
    """Deletes a pipeline run and check results instantly using direct SQL transaction."""
    try:
        rid = int(run_id)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM check_results WHERE run_id = :rid"), {"rid": rid})
            conn.execute(text("DELETE FROM pipeline_runs WHERE id = :rid"), {"rid": rid})
            
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to delete run record #{run_id}: {e}")
        return False

@st.dialog("⚠️ Confirm Deletion")
def confirm_delete_dialog(run_id, storage_loc, file_name):
    st.markdown(f"Are you sure you want to permanently delete the execution record for **`{file_name}`** (Run #{run_id})?")
    st.caption("This action is permanent and will delete the record from database and cloud storage.")
    
    col_close, col_confirm = st.columns([1, 1])
    with col_close:
        if st.button("❌ Cancel", key=f"cancel_modal_{run_id}", use_container_width=True):
            st.session_state.active_delete_run = None
            st.rerun()
    with col_confirm:
        if st.button("🗑️ Confirm Delete", key=f"confirm_modal_{run_id}", type="primary", use_container_width=True):
            st.session_state.active_delete_run = None
            if delete_pipeline_run(run_id, storage_loc):
                st.success(f"Execution run #{run_id} deleted successfully.")
                st.rerun()

st.set_page_config(page_title="Data Reliability Monitor", layout="wide", page_icon="📈")

# --- CUSTOM CSS FOR PREMIUM ENTERPRISE LOOK ---
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', system-ui, sans-serif;
    }
    
    .stApp {
        background-color: #09090b;
    }

    /* Rich Dark Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #0c0c0e !important;
        border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
    }
    
    /* File Uploader Container Styling */
    div[data-testid="stFileUploader"] {
        background-color: #141418 !important;
        border: 1px dashed rgba(129, 140, 248, 0.3) !important;
        border-radius: 12px !important;
        padding: 10px !important;
        transition: border-color 0.2s ease;
    }
    div[data-testid="stFileUploader"]:hover {
        border-color: #818cf8 !important;
    }

    /* Gradient Title */
    .gradient-text {
        background: linear-gradient(90deg, #818cf8 0%, #c084fc 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        letter-spacing: -0.02em;
    }
    
    /* Modern Status Banners */
    .status-banner {
        padding: 18px 24px;
        border-radius: 12px;
        font-size: 16px;
        font-weight: 600;
        margin-bottom: 30px;
        display: flex;
        align-items: center;
        gap: 12px;
        letter-spacing: 0.02em;
        backdrop-filter: blur(10px);
    }
    .status-healthy { 
        background: rgba(34, 197, 94, 0.05);
        border: 1px solid rgba(34, 197, 94, 0.2); 
        color: #4ade80; 
        box-shadow: 0 0 20px rgba(34, 197, 94, 0.05);
    }
    .status-degraded { 
        background: rgba(239, 68, 68, 0.05);
        border: 1px solid rgba(239, 68, 68, 0.2); 
        color: #f87171; 
        box-shadow: 0 0 20px rgba(239, 68, 68, 0.05);
    }

    /* Vector Icon Status Badges */
    .badge-pass {
        background-color: rgba(34, 197, 94, 0.12);
        color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.3);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.05em;
    }
    .badge-fail {
        background-color: rgba(239, 68, 68, 0.12);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.3);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.05em;
    }
    
    /* Glassmorphism Metric Cards with Hover */
    .metric-card {
        background: rgba(24, 24, 27, 0.6);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        padding: 24px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.1);
        margin-bottom: 24px;
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-4px);
        border-color: rgba(129, 140, 248, 0.3);
        box-shadow: 0 10px 25px -5px rgba(129, 140, 248, 0.15);
    }
    .metric-label {
        color: #a1a1aa;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 8px;
    }
    .metric-value {
        color: #f8fafc;
        font-size: 2.25rem;
        font-weight: 800;
        line-height: 1.1;
        letter-spacing: -0.02em;
    }
    
    /* Typography Overrides */
    h1, h2, h3 { color: #f8fafc !important; font-family: 'Inter', sans-serif !important; }
    .subtitle { color: #a1a1aa; font-size: 1.1rem; margin-bottom: 35px; font-weight: 400; letter-spacing: 0.01em; }
    
    /* Enhanced Ticket Description */
    .ticket-desc {
        color: #f1f5f9;
        font-size: 1.05rem;
        line-height: 1.8;
        background-color: #0f172a;
        padding: 24px;
        border-radius: 12px;
        border-left: 4px solid #818cf8;
        margin-bottom: 20px;
        margin-top: 10px;
        border-top: 1px solid rgba(255,255,255,0.02);
        border-right: 1px solid rgba(255,255,255,0.02);
        border-bottom: 1px solid rgba(255,255,255,0.02);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .ticket-desc code {
        font-size: 0.9rem !important;
        color: #f87171 !important;
        background-color: rgba(248, 113, 113, 0.1) !important;
        padding: 4px 8px !important;
        border-radius: 4px;
        border: 1px solid rgba(248, 113, 113, 0.2);
    }
    .ticket-desc ul {
        margin-top: 15px;
        padding-left: 20px;
    }
    .ticket-desc li {
        margin-bottom: 12px;
    }
    
    /* Expander styling for tickets */
    .streamlit-expanderHeader {
        background-color: #18181b !important;
        border-radius: 8px !important;
        border: 1px solid rgba(255,255,255,0.05) !important;
        color: #e2e8f0 !important;
        font-weight: 600 !important;
        transition: background-color 0.2s ease;
    }
    .streamlit-expanderHeader:hover {
        background-color: #27272a !important;
    }
    
    hr {
        border-color: rgba(255,255,255,0.05) !important;
        margin: 2.5rem 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- TOP HEADER NAVIGATION BAR ---
col_head, col_act = st.columns([3, 1])

with col_head:
    st.markdown('<h1 style="font-family: \'Inter\', sans-serif; font-size: 28px; margin-bottom: 2px;"><i class="fa-solid fa-shield-halved" style="color: #818cf8; margin-right: 12px;"></i><span class="gradient-text">Data Reliability Control Center</span></h1>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle" style="margin-bottom: 20px;">Continuous data quality observability, anomaly detection & automated incident management.</div>', unsafe_allow_html=True)

with col_act:
    st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- SIDEBAR: SYSTEM SERVICES & INGESTION LANDING ---
with st.sidebar:
    st.markdown("<h4 style='font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #a1a1aa; margin-bottom: 12px;'><i class='fa-solid fa-server' style='color: #818cf8; margin-right: 8px;'></i> Microservice Infrastructure</h4>", unsafe_allow_html=True)
    if check_fastapi_health():
        st.markdown("<div style='background:rgba(34,197,94,0.08); border:1px solid rgba(34,197,94,0.2); padding:10px 14px; border-radius:8px; color:#4ade80; font-size:13px; font-weight:600;'><i class='fa-solid fa-circle-check'></i> API Engine: Active (8000)</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div style='background:rgba(234,179,8,0.08); border:1px solid rgba(234,179,8,0.2); padding:10px 14px; border-radius:8px; color:#facc15; font-size:13px; font-weight:600;'><i class='fa-solid fa-triangle-exclamation'></i> API Engine: Offline</div>", unsafe_allow_html=True)
        
    st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
    st.markdown("<h4 style='font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #a1a1aa; margin-bottom: 12px;'><i class='fa-solid fa-cloud-arrow-up' style='color: #818cf8; margin-right: 8px;'></i> Batch Ingestion Zone</h4>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 13px; color: #94a3b8; margin-bottom: 14px;'>Drop custom CSV datasets here to trigger real-time validation and cloud storage backup.</p>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Select Batch Dataset", type=['csv'])
    if uploaded_file is not None:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        if st.button("Upload Dataset to Cloud", type="primary", use_container_width=True):
            try:
                bucket_name = os.getenv('S3_BUCKET_NAME', 'data-pipeline-bucket')
                original_name = uploaded_file.name
                
                # Smart collision handling for landing zone upload
                try:
                    root_files = supabase.storage.from_(bucket_name).list()
                    existing_names = [f.get('name', '') for f in root_files]
                except Exception:
                    existing_names = []

                base_name = original_name
                ext = ""
                if "." in original_name:
                    base_name, ext = original_name.rsplit(".", 1)
                    ext = "." + ext

                target_name = original_name
                counter = 1
                while target_name in existing_names:
                    target_name = f"{base_name}_v{counter}{ext}"
                    counter += 1

                file_key = target_name
                file_bytes = uploaded_file.getvalue()
                
                supabase.storage.from_(bucket_name).upload(
                    file=file_bytes,
                    path=file_key,
                    file_options={"content-type": "text/csv"}
                )
                
                st.info(f"File pushed to Supabase Cloud: `{file_key}`. Triggering audit...")
                
                # Instantly run the monitor so the scheduler doesn't overwrite it
                env = os.environ.copy()
                env["MANUAL_RUN"] = "true"
                subprocess.run([sys.executable, "pipeline_monitor.py"], env=env)
                
                st.success("Audit complete! Check the Incident Queue and Audit Logs tabs.")
            except Exception as e:
                st.error(f"Upload failed: {e}")

# Fetch latest status
try:
    latest_run = fetch_data("SELECT status FROM pipeline_runs ORDER BY timestamp DESC LIMIT 1")
    is_healthy = True
    if not latest_run.empty and latest_run.iloc[0]['status'] == 'FAILURE':
        is_healthy = False
        
    if is_healthy:
        st.markdown('<div class="status-banner status-healthy"><i class="fa-solid fa-circle-check"></i> SYSTEM STATUS: FULLY OPERATIONAL</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-banner status-degraded"><i class="fa-solid fa-triangle-exclamation"></i> SYSTEM STATUS: DEGRADED (ANOMALIES DETECTED)</div>', unsafe_allow_html=True)
except:
    pass

# --- MODERN ICON NAVIGATION TABS (streamlit-option-menu) ---
selected_tab = option_menu(
    menu_title=None,
    options=["Pipeline Health", "Incident Queue", "Audit Directory"],
    icons=["activity", "shield-exclamation", "database"],
    default_index=0,
    orientation="horizontal",
    styles={
        "container": {"padding": "4px!important", "background-color": "#18181b", "border-radius": "10px", "margin-bottom": "25px", "border": "1px solid rgba(255,255,255,0.05)"},
        "icon": {"color": "#818cf8", "font-size": "16px"},
        "nav-link": {"font-size": "14px", "text-align": "center", "margin": "0px 4px", "color": "#a1a1aa", "font-weight": "600", "padding": "10px 16px"},
        "nav-link-selected": {"background-color": "#27272a", "color": "#f8fafc", "font-weight": "700", "border-radius": "8px"},
    }
)

if selected_tab == "Pipeline Health":
    try:
        runs_df = fetch_data("SELECT * FROM pipeline_runs ORDER BY timestamp DESC LIMIT 50")
        if not runs_df.empty:
            runs_df['timestamp'] = pd.to_datetime(runs_df['timestamp'])
            
            # --- DATA OBSERVABILITY KPI METRICS ---
            col1, col2, col3, col4 = st.columns(4)
            
            success_rate = (len(runs_df[runs_df['status'] == 'SUCCESS']) / len(runs_df)) * 100
            failed_checks = int(runs_df['failed_checks'].sum())
            est_rows = len(runs_df) * 150
            
            col1.markdown(f'<div class="metric-card"><div class="metric-label">Total Executions</div><div class="metric-value">{len(runs_df)}</div></div>', unsafe_allow_html=True)
            col2.markdown(f'<div class="metric-card"><div class="metric-label">Quality SLA Pass Rate</div><div class="metric-value">{success_rate:.1f}%</div></div>', unsafe_allow_html=True)
            col3.markdown(f'<div class="metric-card"><div class="metric-label">Failed Quality Checks</div><div class="metric-value">{failed_checks}</div></div>', unsafe_allow_html=True)
            col4.markdown(f'<div class="metric-card"><div class="metric-label">Ingested Volume (Est)</div><div class="metric-value">{est_rows:,}</div></div>', unsafe_allow_html=True)
                
            st.markdown("---")
            st.markdown("<h4 style='font-size: 14px; font-weight: 700; color: #f8fafc; margin-bottom: 15px;'><i class='fa-solid fa-chart-line' style='color:#818cf8; margin-right:8px;'></i> Pipeline Reliability Trend (% Checks Passed)</h4>", unsafe_allow_html=True)
            
            # Prepare data for chart
            runs_df['pass_rate'] = (runs_df['passed_checks'] / runs_df['total_checks']) * 100
            runs_df['pass_rate'] = runs_df['pass_rate'].fillna(0)
            
            # Beautiful Altair Chart
            chart = alt.Chart(runs_df).mark_area(
                line={'color':'#6366f1'}, # Indigo-500
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='#6366f1', offset=0),
                           alt.GradientStop(color='rgba(99, 102, 241, 0.05)', offset=1)],
                    x1=1, x2=1, y1=1, y2=0
                )
            ).encode(
                x=alt.X('timestamp:T', title='Time', axis=alt.Axis(grid=False, labelColor='#94a3b8', titleColor='#94a3b8')),
                y=alt.Y('pass_rate:Q', title='Pass Rate (%)', scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(gridColor='#2d2d3d', labelColor='#94a3b8', titleColor='#94a3b8')),
                tooltip=['timestamp', 'pass_rate', 'failed_checks']
            ).properties(height=380).interactive()
            
            # Configure chart theme
            chart = chart.configure_view(strokeWidth=0).configure_axis(domain=False)
            
            st.altair_chart(chart, use_container_width=True)
            
        else:
            st.info("No pipeline runs recorded yet. Start the scheduler to see data!")
    except Exception as e:
        st.error(f"Error loading pipeline data: {e}")

elif selected_tab == "Incident Queue":
    try:
        tickets_df = fetch_data("SELECT * FROM tickets ORDER BY created_at DESC")
        
        if not tickets_df.empty:
            tickets_df['created_at'] = pd.to_datetime(tickets_df['created_at'])
            open_tickets = tickets_df[tickets_df['status'] != 'RESOLVED']
            
            # Custom HTML Metrics
            metric_col1, metric_col2 = st.columns(2)
            metric_col1.markdown(f'<div class="metric-card"><div class="metric-label">Active Incident Tickets</div><div class="metric-value">{len(open_tickets)}</div></div>', unsafe_allow_html=True)
            
            resolved = tickets_df[tickets_df['status'] == 'RESOLVED'].copy()
            if not resolved.empty:
                resolved['resolved_at'] = pd.to_datetime(resolved['resolved_at'])
                resolved['resolution_time'] = resolved['resolved_at'] - resolved['created_at']
                mttr = resolved['resolution_time'].mean()
                hours, remainder = divmod(mttr.total_seconds(), 3600)
                minutes, _ = divmod(remainder, 60)
                mttr_text = f"{int(hours)}h {int(minutes)}m"
            else:
                mttr_text = "N/A"
                
            metric_col2.markdown(f'<div class="metric-card"><div class="metric-label">Mean Time To Resolution (MTTR)</div><div class="metric-value">{mttr_text}</div></div>', unsafe_allow_html=True)
            
            st.markdown("---")
            
            severity_map = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
            if not open_tickets.empty:
                open_tickets['sev_score'] = open_tickets['severity'].map(severity_map)
                open_tickets = open_tickets.sort_values(by=['sev_score', 'created_at'], ascending=[False, False])
                
                for _, ticket in open_tickets.iterrows():
                    with st.expander(f"[{ticket['severity']}] {ticket['title']} - {ticket['created_at'].strftime('%H:%M')}"):
                        st.markdown(f"<div class='ticket-desc'>\n\n{ticket['description']}\n\n</div>", unsafe_allow_html=True)
                        st.markdown(f"**Ticket ID:** `{ticket['id']}` &nbsp;&nbsp;|&nbsp;&nbsp; **Created:** `{ticket['created_at'].strftime('%Y-%m-%d %H:%M:%S')}`")
                        
                        if st.button("Resolve Incident", key=f"resolve_{ticket['id']}", use_container_width=True):
                            if resolve_ticket(ticket['id']):
                                st.rerun()
            else:
                st.markdown('<div class="status-banner status-healthy" style="margin-top:20px;"><i class="fa-solid fa-check"></i> Queue is empty! No active incidents.</div>', unsafe_allow_html=True)
                    
        else:
            st.info("No tickets recorded yet.")
            
    except Exception as e:
        st.error(f"Error loading ticket data: {e}")

elif selected_tab == "Audit Directory":
    try:
        st.markdown("<h3 style='font-size: 20px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;'><i class='fa-solid fa-database' style='color: #818cf8; margin-right: 10px;'></i>File Audit Directory</h3>", unsafe_allow_html=True)
        st.markdown("<p style='color: #94a3b8; font-size: 14px; margin-bottom: 20px;'>Search, filter, and inspect granular validation checks across historical pipeline runs.</p>", unsafe_allow_html=True)
        
        # Display Deletion Alert Toast if run was deleted
        if st.session_state.get("deletion_alert"):
            st.toast(st.session_state.deletion_alert)
            st.success(st.session_state.deletion_alert)
            st.session_state.deletion_alert = None
        
        # --- ROBUST MULTI-FIELD SEARCH & FILTER CONTROLS ---
        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1, 1])
        
        with ctrl_col1:
            search_query = st.text_input("Deep Search (File, ID, Check, or Details)", placeholder="e.g. daily_users, #101, null_values, schema...")
            
        with ctrl_col2:
            status_filter = st.selectbox("Status Filter", ["ALL", "SUCCESS", "FAILURE"])
            
        with ctrl_col3:
            limit_choice = st.selectbox("Records Limit", [30, 50, 100, 500, "ALL"])
            
        limit_sql = "" if limit_choice == "ALL" else f"LIMIT {limit_choice}"
        
        # Fetch live uncached runs and checks directly from database for deep filtering
        runs_df = pd.read_sql(f"SELECT * FROM pipeline_runs ORDER BY timestamp DESC {limit_sql}", engine)
        checks_df = fetch_data("SELECT * FROM check_results ORDER BY timestamp DESC LIMIT 1000")
        
        if not runs_df.empty:
            # Apply Status Filter
            if status_filter != "ALL":
                runs_df = runs_df[runs_df['status'] == status_filter]
                
            # Apply Robust Multi-Field Deep Search
            if search_query.strip():
                q = search_query.strip().lower()
                
                # Check results deep match
                matching_check_run_ids = set()
                if not checks_df.empty:
                    check_matches = checks_df[
                        checks_df['check_name'].astype(str).str.lower().str.contains(q, na=False) |
                        checks_df['details'].astype(str).str.lower().str.contains(q, na=False)
                    ]
                    matching_check_run_ids = set(check_matches['run_id'].dropna().unique())
                    
                runs_df = runs_df[
                    runs_df['file_name'].astype(str).str.lower().str.contains(q, na=False) |
                    runs_df['id'].astype(str).str.contains(q, na=False) |
                    runs_df['storage_location'].astype(str).str.lower().str.contains(q, na=False) |
                    runs_df['id'].isin(matching_check_run_ids)
                ]
                
            if not runs_df.empty:
                st.markdown(f"<p style='color: #818cf8; font-size: 13px; font-weight: 600; margin-bottom: 15px;'><i class='fa-solid fa-filter' style='margin-right:6px;'></i> Showing {len(runs_df)} matching execution run(s)</p>", unsafe_allow_html=True)
                
                for _, run in runs_df.iterrows():
                    status_text = "PASS" if run['status'] == 'SUCCESS' else "FAIL"
                    run_time = pd.to_datetime(run['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
                    file_name = run.get('file_name', 'Unknown')
                    storage_loc = run.get('storage_location', 'N/A')
                    total = run.get('total_checks', 0)
                    passed = run.get('passed_checks', 0)
                    
                    expander_label = f"[{status_text}]  |  {file_name}  |  Checks: {passed}/{total} Passed  |  {run_time}"
                    
                    with st.expander(expander_label):
                        col_info1, col_info2, col_info3 = st.columns(3)
                        col_info1.markdown(f"**Run ID:** `{run['id']}`")
                        col_info2.markdown(f"**File Name:** `{file_name}`")
                        col_info3.markdown(f"**Storage Location:** `{storage_loc}`")
                        
                        st.markdown("---")
                        st.markdown("<h5 style='color:#cbd5e1; margin-bottom:12px;'>Granular Check Breakdown</h5>", unsafe_allow_html=True)
                        
                        if not checks_df.empty:
                            run_checks = checks_df[checks_df['run_id'] == run['id']]
                            if not run_checks.empty:
                                display_df = run_checks[['check_name', 'status', 'details']].copy()
                                
                                def highlight_status(val):
                                    color = '#4ade80' if val == 'PASS' else '#f87171'
                                    return f'color: {color}; font-weight: bold'
                                    
                                styled_df = display_df.style.map(highlight_status, subset=['status'])
                                st.dataframe(styled_df, use_container_width=True, hide_index=True)
                            else:
                                st.write("No granular checks recorded for this run.")
                        else:
                            st.write("No checks available.")
                            
                        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
                        col_sp, col_del_action = st.columns([4, 1])
                        with col_del_action:
                            with st.popover("Delete Record", use_container_width=True):
                                pop_hdr, pop_cls = st.columns([4, 1])
                                with pop_hdr:
                                    st.markdown(f"**Delete Run #{run['id']}?**")
                                with pop_cls:
                                    if st.button("Cancel", key=f"cls_pop_{run['id']}", help="Cancel deletion"):
                                        st.rerun()
                                        
                                st.caption(f"Record for `{file_name}` will be permanently deleted.")
                                st.markdown("<div style='margin-top: 6px;'></div>", unsafe_allow_html=True)
                                
                                if st.button("Confirm Delete", key=f"confirm_pop_{run['id']}", type="primary", use_container_width=True):
                                    if delete_pipeline_run(run['id'], storage_loc):
                                        st.session_state.deletion_alert = f"Execution run #{run['id']} ({file_name}) successfully deleted."
                                        st.rerun()
            else:
                st.warning(f"No execution runs found matching your search filter.")
        else:
            st.info("No audit logs available yet.")
    except Exception as e:
        st.error(f"Error loading audit logs: {e}")
