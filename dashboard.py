import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
from ticketing import resolve_ticket
import altair as alt
from datetime import datetime
import subprocess
import sys
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Setup Database Connection
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./monitor.db")
engine = create_engine(DATABASE_URL)

st.set_page_config(page_title="Data Reliability Monitor", layout="wide", page_icon="📈")

# --- CUSTOM CSS FOR PREMIUM ENTERPRISE LOOK ---
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', system-ui, sans-serif;
    }
    
    /* Modern Status Banners */
    .status-banner {
        padding: 16px 24px;
        border-radius: 8px;
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 24px;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .status-healthy { 
        background-color: rgba(34, 197, 94, 0.1); 
        border: 1px solid rgba(34, 197, 94, 0.4); 
        color: #4ade80; 
    }
    .status-degraded { 
        background-color: rgba(239, 68, 68, 0.1); 
        border: 1px solid rgba(239, 68, 68, 0.4); 
        color: #f87171; 
    }
    
    /* Custom HTML Metric Cards */
    .metric-card {
        background-color: #1a1a24;
        border: 1px solid #2d2d3d;
        border-radius: 8px;
        padding: 24px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        margin-bottom: 20px;
    }
    .metric-label {
        color: #94a3b8;
        font-size: 0.875rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
    }
    .metric-value {
        color: #f8fafc;
        font-size: 2rem;
        font-weight: 700;
        line-height: 1.2;
    }
    
    /* Typography Overrides */
    h1, h2, h3 { color: #f8fafc !important; font-family: 'Inter', sans-serif !important; }
    .subtitle { color: #94a3b8; font-size: 1.1rem; margin-bottom: 30px; font-weight: 400; }
    
    /* Enhanced Ticket Description */
    .ticket-desc {
        color: #f8fafc;
        font-size: 1.15rem;
        line-height: 1.8;
        background-color: #111118;
        padding: 24px;
        border-radius: 8px;
        border-left: 4px solid #6366f1;
        margin-bottom: 20px;
        margin-top: 10px;
        box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.2);
    }
    .ticket-desc code {
        font-size: 0.95rem !important;
        color: #f87171 !important;
        background-color: rgba(248, 113, 113, 0.1) !important;
        padding: 3px 6px !important;
    }
    .ticket-desc ul {
        margin-top: 15px;
        padding-left: 20px;
    }
    .ticket-desc li {
        margin-bottom: 10px;
    }
    
    /* Expander styling for tickets */
    .streamlit-expanderHeader {
        background-color: #1a1a24 !important;
        border-radius: 5px !important;
        border: 1px solid #2d2d3d !important;
        color: #e2e8f0 !important;
    }
    
    hr {
        border-color: #2d2d3d !important;
        margin: 2rem 0 !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 style="color: #f8fafc; font-family: \'Inter\', sans-serif;"><i class="fa-solid fa-server" style="color: #6366f1; margin-right: 12px;"></i>Data Reliability Control Center</h1>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Real-time pipeline monitoring, anomaly detection, and incident management.</div>', unsafe_allow_html=True)

# --- SIDEBAR: MANUAL TESTING ---
with st.sidebar:
    st.markdown("### 🧪 Manual Testing Zone")
    st.markdown("<p style='font-size: 14px; color: #94a3b8;'>Drop a custom CSV here. It will be uploaded directly to S3. Within 60 seconds, your background scheduler will detect it, audit it, and flag any errors!</p>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Upload custom CSV", type=['csv'])
    if uploaded_file is not None:
        if st.button("📤 Upload to Cloud Storage", use_container_width=True):
            try:
                bucket_name = os.getenv('S3_BUCKET_NAME', 'data-pipeline-bucket')
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_key = f"daily_users_{timestamp}_manual.csv"
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
    latest_run = pd.read_sql("SELECT status FROM pipeline_runs ORDER BY timestamp DESC LIMIT 1", engine)
    is_healthy = True
    if not latest_run.empty and latest_run.iloc[0]['status'] == 'FAILURE':
        is_healthy = False
        
    if is_healthy:
        st.markdown('<div class="status-banner status-healthy"><i class="fa-solid fa-circle-check"></i> SYSTEM STATUS: FULLY OPERATIONAL</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-banner status-degraded"><i class="fa-solid fa-triangle-exclamation"></i> SYSTEM STATUS: DEGRADED (ANOMALIES DETECTED)</div>', unsafe_allow_html=True)
except:
    pass

tab1, tab2, tab3 = st.tabs(["Pipeline Health", "Incident Queue", "Audit Logs"])

with tab1:
    try:
        runs_df = pd.read_sql("SELECT * FROM pipeline_runs ORDER BY timestamp DESC LIMIT 50", engine)
        if not runs_df.empty:
            runs_df['timestamp'] = pd.to_datetime(runs_df['timestamp'])
            
            # Custom HTML Metric Cards
            col1, col2, col3, col4 = st.columns(4)
            
            success_rate = (len(runs_df[runs_df['status'] == 'SUCCESS']) / len(runs_df)) * 100
            failed_checks = int(runs_df['failed_checks'].sum())
            est_rows = len(runs_df) * 150
            
            col1.markdown(f'<div class="metric-card"><div class="metric-label">Total Executions</div><div class="metric-value">{len(runs_df)}</div></div>', unsafe_allow_html=True)
            col2.markdown(f'<div class="metric-card"><div class="metric-label">Pipeline Health</div><div class="metric-value">{success_rate:.1f}%</div></div>', unsafe_allow_html=True)
            col3.markdown(f'<div class="metric-card"><div class="metric-label">Failed Checks</div><div class="metric-value">{failed_checks}</div></div>', unsafe_allow_html=True)
            col4.markdown(f'<div class="metric-card"><div class="metric-label">Data Processed (Est)</div><div class="metric-value">{est_rows:,}</div></div>', unsafe_allow_html=True)
                
            st.markdown("---")
            st.markdown("### Data Quality Trend (% Checks Passed)")
            
            # Prepare data for beautiful chart
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

with tab2:
    try:
        tickets_df = pd.read_sql("SELECT * FROM tickets ORDER BY created_at DESC", engine)
        
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

with tab3:
    try:
        checks_df = pd.read_sql("SELECT * FROM check_results ORDER BY timestamp DESC LIMIT 100", engine)
        if not checks_df.empty:
            
            # Format dataframe to look better
            def highlight_status(val):
                color = '#4ade80' if val == 'PASS' else '#f87171'
                return f'color: {color}; font-weight: bold'
                
            styled_df = checks_df.style.map(highlight_status, subset=['status'])
            st.dataframe(styled_df, use_container_width=True, hide_index=True, height=500)
        else:
            st.info("No audit logs yet.")
    except Exception as e:
        st.error(f"Error loading check results: {e}")
