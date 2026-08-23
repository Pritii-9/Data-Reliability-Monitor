import os
import streamlit as st
import pandas as pd
import requests
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from ticketing import resolve_ticket, resolve_all_tickets
from database import SessionLocal, PipelineRun, CheckResult
import altair as alt
from datetime import datetime
import subprocess
import sys
from supabase import create_client, Client
from streamlit_option_menu import option_menu
import importlib
import ai_engine
importlib.reload(ai_engine)
from ai_engine import generate_file_ai_summary, generate_ai_root_cause_analysis

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

# --- TAILWIND CSS V4 INTEGRATION & STYLING ENGINE ---
st.markdown("""
<script src="https://unpkg.com/@tailwindcss/browser@4"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style type="text/tailwindcss">
    @theme {
        --color-brand-primary: #818cf8;
        --color-brand-purple: #c084fc;
        --color-brand-emerald: #4ade80;
        --color-brand-rose: #f87171;
        --color-dark-bg: #09090b;
        --color-dark-card: #18181b;
        --font-sans: 'Inter', system-ui, sans-serif;
    }
</style>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', system-ui, sans-serif;
    }
    
    .stApp {
        background-color: #09090b;
    }

    /* Dark Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #0c0c0e !important;
        border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
    }
    
    /* File Uploader Container */
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

    /* Expander Header Styling */
    .streamlit-expanderHeader {
        background-color: #18181b !important;
        border-radius: 10px !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        color: #f8fafc !important;
        font-weight: 600 !important;
    }
    .streamlit-expanderHeader:hover {
        background-color: #27272a !important;
        border-color: rgba(129, 140, 248, 0.3) !important;
    }
    
    /* Pixel-Perfect Equal Height Columns in Streamlit */
    div[data-testid="stHorizontalBlock"] {
        align-items: stretch !important;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
        display: flex !important;
        flex-direction: column !important;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {
        height: 100% !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: space-between !important;
    }

    /* Sidebar High-Contrast Styling */
    section[data-testid="stSidebar"] {
        background-color: #09090b !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"] {
        padding-top: 1.25rem !important;
    }

    hr {
        border-color: rgba(255,255,255,0.06) !important;
        margin: 2rem 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- TOP HEADER NAVIGATION BAR (TAILWIND CSS V4) ---
col_head, col_act = st.columns([3, 1])

with col_head:
    st.markdown("""
    <div class="mb-4">
        <h1 class="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
            <i class="fa-solid fa-shield-halved text-indigo-400"></i>
            <span class="bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">Data Reliability Control Center</span>
        </h1>
        <p class="text-sm text-zinc-400 mt-1">Continuous data quality observability, anomaly detection & automated incident management.</p>
    </div>
    """, unsafe_allow_html=True)

with col_act:
    st.markdown("<div class='mt-1'></div>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- SIDEBAR: HIGH-CONTRAST ENTERPRISE DESIGN (TAILWIND CSS V4) ---
with st.sidebar:
    # 1. Brand Identity Header
    st.markdown("""
    <div class="mb-6 border-b border-zinc-800/80 pb-5">
        <div class="flex items-center gap-3">
            <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-md">
                <i class="fa-solid fa-shield-halved text-lg"></i>
            </div>
            <div>
                <div class="text-sm font-bold text-white tracking-tight">Reliability Engine</div>
                <div class="text-[11px] font-medium text-zinc-400">Enterprise Observability v2.4</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 2. System Status Card
    st.markdown("""
    <div class="rounded-2xl border border-zinc-800/80 bg-zinc-900/60 p-4 backdrop-blur-xl shadow-lg mb-5">
        <div class="flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-zinc-400 mb-3">
            <span>System Infrastructure</span>
            <i class="fa-solid fa-server text-indigo-400"></i>
        </div>
    """, unsafe_allow_html=True)
    
    if check_fastapi_health():
        st.markdown("""
        <div class="flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-400 mb-2">
            <span class="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>API Engine: Active (8000)</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="flex items-center gap-2 rounded-xl border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-xs font-semibold text-yellow-400 mb-2">
            <span class="h-2 w-2 rounded-full bg-yellow-400"></span>
            <span>API Engine: Offline</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
        <div class="flex items-center gap-2 text-[11px] text-zinc-400 px-1 pt-1 border-t border-zinc-800/60">
            <i class="fa-solid fa-database text-indigo-400 text-xs"></i> Storage: <span class="text-slate-200 font-mono">Supabase S3</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # 3. Batch Ingestion Drop Zone
    st.markdown("""
    <div class="rounded-2xl border border-zinc-800/80 bg-zinc-900/60 p-4 backdrop-blur-xl shadow-lg mb-3">
        <div class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-400 mb-1.5">
            <i class="fa-solid fa-cloud-arrow-up"></i> Batch File Ingestion
        </div>
        <p class="text-xs text-zinc-400 leading-relaxed">Drop CSV, PDF, or log files to trigger cloud backup & AI quality audit.</p>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Select Batch Dataset", type=['csv', 'pdf', 'txt'], label_visibility="collapsed")
    if uploaded_file is not None:
        st.markdown("<div class='mt-2'></div>", unsafe_allow_html=True)
        if st.button("Upload & Trigger Audit", type="primary", use_container_width=True):
            try:
                bucket_name = os.getenv('S3_BUCKET_NAME', 'data-pipeline-bucket')
                original_name = uploaded_file.name
                
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
                
                env = os.environ.copy()
                env["MANUAL_RUN"] = "true"
                subprocess.run([sys.executable, "pipeline_monitor.py"], env=env)
                
                st.success("Audit complete! Check Incident Queue and Audit Directory.")
            except Exception as e:
                st.error(f"Upload failed: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

# --- MODERN NAVIGATION TABS (streamlit-option-menu) ---
selected_tab = option_menu(
    menu_title=None,
    options=["Pipeline Health", "Incident Queue", "AI Intelligence Hub", "Audit Directory"],
    icons=["activity", "shield-exclamation", "cpu", "database"],
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
            
            col1, col2, col3, col4 = st.columns(4)
            
            success_rate = (len(runs_df[runs_df['status'] == 'SUCCESS']) / len(runs_df)) * 100
            failed_checks = int(runs_df['failed_checks'].sum())
            est_rows = len(runs_df) * 150
            
            col1.markdown(f"""
            <div class="h-[105px] flex flex-col justify-between rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5 shadow-xl backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-indigo-500/40">
                <div class="flex items-center justify-between">
                    <span class="text-[11px] font-bold uppercase tracking-wider text-zinc-400">Total Executions</span>
                    <i class="fa-solid fa-bolt text-indigo-400 text-xs"></i>
                </div>
                <div class="text-3xl font-extrabold text-white tracking-tight">{len(runs_df)}</div>
            </div>
            """, unsafe_allow_html=True)

            col2.markdown(f"""
            <div class="h-[105px] flex flex-col justify-between rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5 shadow-xl backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-indigo-500/40">
                <div class="flex items-center justify-between">
                    <span class="text-[11px] font-bold uppercase tracking-wider text-zinc-400">Quality SLA Pass Rate</span>
                    <i class="fa-solid fa-shield-halved text-emerald-400 text-xs"></i>
                </div>
                <div class="text-3xl font-extrabold text-white tracking-tight">{success_rate:.1f}%</div>
            </div>
            """, unsafe_allow_html=True)

            col3.markdown(f"""
            <div class="h-[105px] flex flex-col justify-between rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5 shadow-xl backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-indigo-500/40">
                <div class="flex items-center justify-between">
                    <span class="text-[11px] font-bold uppercase tracking-wider text-zinc-400">Failed Quality Checks</span>
                    <i class="fa-solid fa-triangle-exclamation text-rose-400 text-xs"></i>
                </div>
                <div class="text-3xl font-extrabold text-white tracking-tight">{failed_checks}</div>
            </div>
            """, unsafe_allow_html=True)

            col4.markdown(f"""
            <div class="h-[105px] flex flex-col justify-between rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5 shadow-xl backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-indigo-500/40">
                <div class="flex items-center justify-between">
                    <span class="text-[11px] font-bold uppercase tracking-wider text-zinc-400">Ingested Volume (Est)</span>
                    <i class="fa-solid fa-database text-purple-400 text-xs"></i>
                </div>
                <div class="text-3xl font-extrabold text-white tracking-tight">{est_rows:,}</div>
            </div>
            """, unsafe_allow_html=True)
                
            st.markdown("---")
            st.markdown("<h4 class='text-sm font-bold text-white mb-4 flex items-center gap-2'><i class='fa-solid fa-chart-line text-indigo-400'></i> Pipeline Reliability Trend (% Checks Passed)</h4>", unsafe_allow_html=True)
            
            runs_df['pass_rate'] = (runs_df['passed_checks'] / runs_df['total_checks']) * 100
            runs_df['pass_rate'] = runs_df['pass_rate'].fillna(0)
            
            chart = alt.Chart(runs_df).mark_area(
                line={'color':'#6366f1'},
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
            open_tickets = tickets_df[tickets_df['status'] != 'RESOLVED'].copy()
            
            metric_col1, metric_col2, metric_col3 = st.columns(3)
            
            metric_col1.markdown(f"""
            <div class="h-[105px] flex flex-col justify-between rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5 shadow-xl backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-indigo-500/40">
                <div class="flex items-center justify-between">
                    <span class="text-[11px] font-bold uppercase tracking-wider text-zinc-400">Active Incident Tickets</span>
                    <i class="fa-solid fa-triangle-exclamation text-rose-400 text-xs"></i>
                </div>
                <div class="text-3xl font-extrabold text-white tracking-tight">{len(open_tickets)}</div>
            </div>
            """, unsafe_allow_html=True)
            
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
                
            metric_col2.markdown(f"""
            <div class="h-[105px] flex flex-col justify-between rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5 shadow-xl backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-indigo-500/40">
                <div class="flex items-center justify-between">
                    <span class="text-[11px] font-bold uppercase tracking-wider text-zinc-400">Mean Time To Resolution (MTTR)</span>
                    <i class="fa-solid fa-clock text-indigo-400 text-xs"></i>
                </div>
                <div class="text-3xl font-extrabold text-white tracking-tight">{mttr_text}</div>
            </div>
            """, unsafe_allow_html=True)
            
            metric_col3.markdown(f"""
            <div class="h-[105px] flex flex-col justify-between rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5 shadow-xl backdrop-blur-xl transition-all duration-300 hover:-translate-y-1 hover:border-indigo-500/40">
                <div class="flex items-center justify-between">
                    <span class="text-[11px] font-bold uppercase tracking-wider text-zinc-400">System Incident SLA</span>
                    <i class="fa-solid fa-circle-check text-emerald-400 text-xs"></i>
                </div>
                <div class="text-3xl font-extrabold text-emerald-400 tracking-tight">Active</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("---")
            
            if not open_tickets.empty:
                c_filter, c_page, c_action = st.columns([2, 2, 2])
                with c_filter:
                    sev_filter = st.selectbox("Severity Filter", ["ALL", "HIGH", "MEDIUM", "LOW"], key="queue_sev_filter")
                
                filtered_tickets = open_tickets.copy()
                if sev_filter != "ALL":
                    filtered_tickets = filtered_tickets[filtered_tickets['severity'] == sev_filter]

                severity_map = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
                filtered_tickets['sev_score'] = filtered_tickets['severity'].map(severity_map)
                filtered_tickets = filtered_tickets.sort_values(by=['sev_score', 'created_at'], ascending=[False, False])
                
                page_size = 10
                total_filtered = len(filtered_tickets)
                total_pages = max(1, (total_filtered + page_size - 1) // page_size)
                
                with c_page:
                    current_page = st.number_input(f"Page (1 of {total_pages})", min_value=1, max_value=total_pages, value=1, step=1)
                
                with c_action:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    if len(open_tickets) > 0:
                        if st.button("Clear All Incidents", type="secondary", use_container_width=True, key="btn_resolve_all"):
                            if resolve_all_tickets():
                                st.success("All open incident tickets resolved!")
                                st.rerun()
                
                start_idx = (current_page - 1) * page_size
                end_idx = start_idx + page_size
                page_tickets = filtered_tickets.iloc[start_idx:end_idx]
                
                st.caption(f"Displaying **{len(page_tickets)}** of **{total_filtered}** active incidents (Page {current_page}/{total_pages}).")
                
                for _, ticket in page_tickets.iterrows():
                    desc_raw = str(ticket['description'])
                    
                    # Smart metadata extraction
                    fname = "None Found"
                    run_id = "N/A"
                    ai_rca = "Unspecified validation failure detected during batch ingestion."
                    
                    if "**File Name:**" in desc_raw:
                        try:
                            fname = desc_raw.split("**File Name:**")[1].split("**")[0].strip(" `")
                        except Exception:
                            pass
                    if "**Pipeline Run ID:**" in desc_raw:
                        try:
                            run_id = desc_raw.split("**Pipeline Run ID:**")[1].split("**")[0].strip(" `")
                        except Exception:
                            pass
                    if "AI Root Cause Analysis" in desc_raw:
                        try:
                            part = desc_raw.split("AI Root Cause Analysis")[1]
                            if "Issues" in part:
                                ai_rca = part.split("Issues")[0].strip(" #\n\r")
                            else:
                                ai_rca = part.strip(" #\n\r")
                        except Exception:
                            pass

                    # Render Pristine Tailwind CSS v4 Incident Card
                    with st.expander(f"[{ticket['severity']}] {ticket['title']} - {ticket['created_at'].strftime('%Y-%m-%d %H:%M')}"):
                        st.markdown(f"""
                        <div class="my-3 rounded-2xl border border-zinc-800 bg-zinc-900/90 p-5 shadow-xl backdrop-blur-md">
                            <div class="grid grid-cols-3 gap-3 mb-4 border-b border-zinc-800/80 pb-4">
                                <div class="rounded-xl bg-zinc-950 p-3 border border-zinc-800/60">
                                    <div class="text-[10px] font-bold uppercase tracking-wider text-zinc-400">File Ingested</div>
                                    <div class="text-xs font-semibold text-slate-100 font-mono mt-1 truncate">{fname}</div>
                                </div>
                                <div class="rounded-xl bg-zinc-950 p-3 border border-zinc-800/60">
                                    <div class="text-[10px] font-bold uppercase tracking-wider text-zinc-400">Execution Run</div>
                                    <div class="text-xs font-semibold text-indigo-400 font-mono mt-1">#{run_id}</div>
                                </div>
                                <div class="rounded-xl bg-zinc-950 p-3 border border-zinc-800/60">
                                    <div class="text-[10px] font-bold uppercase tracking-wider text-zinc-400">Severity Level</div>
                                    <div class="text-xs font-bold text-rose-400 font-mono mt-1">{ticket['severity']}</div>
                                </div>
                            </div>
                            
                            <div class="rounded-xl border border-indigo-500/20 bg-indigo-950/20 p-4">
                                <div class="flex items-center gap-2 text-xs font-bold text-indigo-300 uppercase tracking-wider mb-1.5">
                                    <i class="fa-solid fa-microchip text-indigo-400"></i> AI Root Cause Diagnosis
                                </div>
                                <div class="text-sm text-slate-200 leading-relaxed font-normal">{ai_rca}</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.markdown(f"**Ticket ID:** `{ticket['id']}` &nbsp;&nbsp;|&nbsp;&nbsp; **Created:** `{ticket['created_at'].strftime('%Y-%m-%d %H:%M:%S')}`")
                        
                        if st.button("Resolve Incident", key=f"resolve_{ticket['id']}", use_container_width=True):
                            if resolve_ticket(ticket['id']):
                                st.rerun()
            else:
                st.markdown("""
                <div class="my-6 flex items-center gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4 font-semibold text-emerald-400 shadow-lg shadow-emerald-500/5 backdrop-blur-md">
                    <i class="fa-solid fa-circle-check text-lg"></i> Queue is empty! No active incident tickets matching criteria.
                </div>
                """, unsafe_allow_html=True)
                    
        else:
            st.info("No tickets recorded yet.")
            
    except Exception as e:
        st.error(f"Error loading ticket data: {e}")

elif selected_tab == "AI Intelligence Hub":
    st.markdown("""
    <div class="mb-6">
        <h3 class="text-xl font-extrabold text-white flex items-center gap-2.5">
            <i class="fa-solid fa-brain text-indigo-400"></i> AI Intelligence Hub
        </h3>
        <p class="text-xs text-zinc-400 mt-1">Automated AI root cause analysis & execution reliability diagnosis.</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.container(border=True):
        st.markdown("""
        <div class="mb-4">
            <div class="flex items-center gap-2 text-sm font-bold text-slate-100 mb-1">
                <i class="fa-solid fa-microchip text-indigo-400"></i> Pipeline Execution RCA Engine
            </div>
            <p class="text-xs text-zinc-400 leading-relaxed">
                Select an execution run to generate instant AI Root Cause Analysis, domain intelligence, and validation checks breakdown.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        try:
            runs_to_analyze = fetch_data("SELECT id, file_name, timestamp, status FROM pipeline_runs ORDER BY timestamp DESC LIMIT 20")
            if not runs_to_analyze.empty:
                run_options = {f"Run #{r['id']} — {r['file_name']} ({r['status']})": r['id'] for _, r in runs_to_analyze.iterrows()}
                selected_run_label = st.selectbox("Select Execution Run to Diagnose", list(run_options.keys()), key="ai_hub_run_select")
                selected_run_id = run_options[selected_run_label]
                
                st.markdown("<div class='my-3'></div>", unsafe_allow_html=True)
                
                if st.button("⚡ Run Root Cause Analysis (RCA)", type="primary", use_container_width=True, key="btn_run_unified_ai"):
                    with st.spinner(f"Running AI Intelligence & Root Cause Analysis on Run #{selected_run_id}..."):
                        checks = fetch_data(f"SELECT check_name, status, details FROM check_results WHERE run_id = {selected_run_id}")
                        failed_checks = checks[checks['status'] == 'FAIL'].to_dict(orient='records')
                        run_info = runs_to_analyze[runs_to_analyze['id']==selected_run_id].iloc[0]
                        run_status = run_info['status']
                        run_fname = run_info['file_name']
                        
                        rca_output = generate_ai_root_cause_analysis(
                            failed_checks,
                            None,
                            run_fname,
                            str(selected_run_id),
                            run_status
                        )
                        
                        formatted_md = f"""{rca_output}

---

### Validation Checks Breakdown
"""
                        for _, c in checks.iterrows():
                            status_icon = '<i class="fa-solid fa-circle-check" style="color:#4ade80; margin-right:6px;"></i>' if c['status'] == 'PASS' else '<i class="fa-solid fa-circle-xmark" style="color:#f87171; margin-right:6px;"></i>'
                            formatted_md += f"- {status_icon} **`{c['check_name']}`**: {c['details']}\n"
                            
                        st.session_state["active_ai_analysis"] = {
                            "status": "SUCCESS",
                            "summary_md": formatted_md
                        }
                        st.session_state["active_ai_filename"] = f"{run_fname} (Run #{selected_run_id})"
            else:
                st.info("No recorded pipeline runs found to analyze.")
        except Exception as e:
            st.error(f"Error fetching runs: {e}")

    # Display Analysis Output Container (PURE TAILWIND CSS V4)
    if "active_ai_analysis" in st.session_state:
        res = st.session_state["active_ai_analysis"]
        fname = st.session_state.get("active_ai_filename", "Uploaded File")
        
        st.markdown(f"""
        <div class="my-6 rounded-2xl border border-indigo-500/20 bg-zinc-900/90 p-6 shadow-2xl backdrop-blur-xl transition-all hover:border-indigo-500/40">
            <div class="flex items-center gap-3 border-b border-zinc-800 pb-4 mb-5">
                <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                    <i class="fa-solid fa-microchip text-lg"></i>
                </div>
                <div>
                    <h3 class="text-base font-bold text-white tracking-tight">
                        AI Diagnostic Report: <span class="text-indigo-400">{fname}</span>
                    </h3>
                    <p class="text-xs text-zinc-400">Data Observability & Intelligence</p>
                </div>
            </div>
            <div class="text-sm text-slate-200 leading-relaxed">
        """, unsafe_allow_html=True)
        
        st.markdown(res.get("summary_md", "No summary generated."), unsafe_allow_html=True)
        
        st.markdown("</div></div>", unsafe_allow_html=True)

elif selected_tab == "Audit Directory":
    try:
        st.markdown("""
        <div class="mb-5">
            <h3 class="text-xl font-bold text-white flex items-center gap-2">
                <i class="fa-solid fa-database text-indigo-400"></i> File Audit Directory
            </h3>
        </div>
        """, unsafe_allow_html=True)
        
        if st.session_state.get("deletion_alert"):
            st.toast(st.session_state.deletion_alert)
            st.success(st.session_state.deletion_alert)
            st.session_state.deletion_alert = None
        
        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1, 1])
        
        with ctrl_col1:
            search_query = st.text_input("Deep Search (File, ID, Check, or Details)", placeholder="e.g. daily_users, #101, null_values, schema...")
            
        with ctrl_col2:
            status_filter = st.selectbox("Status Filter", ["ALL", "SUCCESS", "FAILURE"])
            
        with ctrl_col3:
            sort_order = st.selectbox("Sort By", ["Newest First", "Oldest First"])

        base_query = """
            SELECT p.id as run_id, p.file_name, p.timestamp, p.status as run_status,
                   c.check_name, c.status as check_status, c.details
            FROM pipeline_runs p
            LEFT JOIN check_results c ON p.id = c.run_id
        """
        
        audit_df = fetch_data(base_query)
        
        if not audit_df.empty:
            if status_filter != "ALL":
                audit_df = audit_df[audit_df['run_status'] == status_filter]
                
            if search_query:
                q = search_query.lower()
                audit_df = audit_df[
                    audit_df['file_name'].str.lower().str.contains(q, na=False) |
                    audit_df['check_name'].str.lower().str.contains(q, na=False) |
                    audit_df['details'].str.lower().str.contains(q, na=False) |
                    audit_df['run_id'].astype(str).str.contains(q, na=False)
                ]
                
            if sort_order == "Newest First":
                audit_df = audit_df.sort_values(by="timestamp", ascending=False)
            else:
                audit_df = audit_df.sort_values(by="timestamp", ascending=True)

            unique_runs = audit_df['run_id'].unique()
            
            st.caption(f"Showing **{len(unique_runs)}** execution runs matching criteria.")
            
            for run_id in unique_runs:
                run_rows = audit_df[audit_df['run_id'] == run_id]
                first_row = run_rows.iloc[0]
                
                dt_str = pd.to_datetime(first_row['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                r_status = first_row['run_status']
                f_name = first_row['file_name']
                
                with st.expander(f"Run #{run_id} — {f_name} ({r_status}) — {dt_str}"):
                    info_col, btn_col = st.columns([4, 1])
                    with info_col:
                        st.markdown(f"**Execution ID:** `{run_id}` &nbsp;&nbsp;|&nbsp;&nbsp; **File:** `{f_name}` &nbsp;&nbsp;|&nbsp;&nbsp; **Timestamp:** `{dt_str}`")
                    with btn_col:
                        if st.button("🗑️ Delete Run", key=f"btn_del_{run_id}", type="secondary", use_container_width=True):
                            st.session_state.active_delete_run = (run_id, f"s3://quarantine/{f_name}", f_name)
                            st.rerun()

                    st.markdown("<div class='my-2'></div>", unsafe_allow_html=True)
                    
                    check_table_data = []
                    for _, crow in run_rows.iterrows():
                        if pd.notnull(crow['check_name']):
                            c_stat = crow['check_status']
                            check_table_data.append({
                                "Check Name": crow['check_name'],
                                "Status": c_stat,
                                "Details": crow['details']
                            })
                            
                    if check_table_data:
                        c_df = pd.DataFrame(check_table_data)
                        st.dataframe(
                            c_df,
                            column_config={
                                "Status": st.column_config.TextColumn(
                                    "Status",
                                    help="Validation Pass/Fail result"
                                )
                            },
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.caption("No individual check records logged for this execution.")
                        
        else:
            st.info("No audit logs matching current filter criteria.")

    except Exception as e:
        st.error(f"Error rendering audit directory: {e}")

if st.session_state.get("active_delete_run"):
    r_id, s_loc, f_n = st.session_state.active_delete_run
    confirm_delete_dialog(r_id, s_loc, f_n)
