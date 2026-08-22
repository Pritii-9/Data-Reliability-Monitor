import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv
from ticketing import resolve_ticket

load_dotenv()

# Setup Database Connection
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./monitor.db")
engine = create_engine(DATABASE_URL)

st.set_page_config(page_title="Data Reliability Monitor", layout="wide", page_icon="📊")

st.title("📊 Data Reliability Monitor")
st.markdown("A pipeline monitoring and incident ticketing dashboard.")

# Create tabs for different views
tab1, tab2, tab3 = st.tabs(["Pipeline Health", "Incident Tickets", "System Logs"])

with tab1:
    st.header("Pipeline Health & Trends")
    
    # Load pipeline runs
    try:
        runs_df = pd.read_sql("SELECT * FROM pipeline_runs ORDER BY timestamp DESC LIMIT 30", engine)
        if not runs_df.empty:
            runs_df['timestamp'] = pd.to_datetime(runs_df['timestamp'])
            
            # Key Metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Runs (Last 30)", len(runs_df))
            with col2:
                success_rate = (len(runs_df[runs_df['status'] == 'SUCCESS']) / len(runs_df)) * 100
                st.metric("Success Rate", f"{success_rate:.1f}%")
            with col3:
                st.metric("Total Failed Checks", runs_df['failed_checks'].sum())
                
            # Trend Chart
            st.subheader("Data Quality Trend (% Checks Passed)")
            runs_df['pass_rate'] = (runs_df['passed_checks'] / runs_df['total_checks']) * 100
            runs_df['pass_rate'] = runs_df['pass_rate'].fillna(0)
            
            chart_data = runs_df[['timestamp', 'pass_rate']].set_index('timestamp').sort_index()
            st.line_chart(chart_data)
        else:
            st.info("No pipeline runs recorded yet.")
    except Exception as e:
        st.error(f"Error loading pipeline data: {e}")

with tab2:
    st.header("Incident Tickets Queue")
    
    try:
        tickets_df = pd.read_sql("SELECT * FROM tickets ORDER BY created_at DESC", engine)
        
        if not tickets_df.empty:
            tickets_df['created_at'] = pd.to_datetime(tickets_df['created_at'])
            
            # Filter for Open tickets
            open_tickets = tickets_df[tickets_df['status'] != 'RESOLVED']
            
            # Top-level metrics
            metric_col1, metric_col2 = st.columns(2)
            with metric_col1:
                st.metric("Total Open Tickets", len(open_tickets))
            with metric_col2:
                resolved = tickets_df[tickets_df['status'] == 'RESOLVED'].copy()
                if not resolved.empty:
                    resolved['resolved_at'] = pd.to_datetime(resolved['resolved_at'])
                    resolved['resolution_time'] = resolved['resolved_at'] - resolved['created_at']
                    mttr = resolved['resolution_time'].mean()
                    
                    hours, remainder = divmod(mttr.total_seconds(), 3600)
                    minutes, _ = divmod(remainder, 60)
                    st.metric("Average MTTR", f"{int(hours)}h {int(minutes)}m")
                else:
                    st.metric("Average MTTR", "N/A")
            
            st.divider()
            
            # Interactive Ticket Cards
            severity_map = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
            if not open_tickets.empty:
                open_tickets['sev_score'] = open_tickets['severity'].map(severity_map)
                open_tickets = open_tickets.sort_values(by=['sev_score', 'created_at'], ascending=[False, False])
                
                st.subheader("Active Incidents")
                
                for _, ticket in open_tickets.iterrows():
                    # Color coding emojis based on severity
                    icon = "🔴" if ticket['severity'] == "HIGH" else ("🟠" if ticket['severity'] == "MEDIUM" else "🟢")
                    
                    with st.expander(f"{icon} {ticket['severity']} | {ticket['title']} ({ticket['created_at'].strftime('%Y-%m-%d %H:%M')})"):
                        st.markdown(f"**Description:**\n\n{ticket['description']}")
                        st.markdown(f"**Ticket ID:** `{ticket['id']}` | **Status:** `{ticket['status']}`")
                        
                        # Add a button to resolve the ticket
                        if st.button("✅ Mark as Resolved", key=f"resolve_{ticket['id']}"):
                            if resolve_ticket(ticket['id']):
                                st.rerun() # Refresh the page to reflect the resolution
            else:
                st.success("🎉 No open tickets! The data pipeline is healthy.")
                    
        else:
            st.info("No tickets recorded yet.")
            
    except Exception as e:
        st.error(f"Error loading ticket data: {e}")

with tab3:
    st.header("Check Results Logs")
    try:
        checks_df = pd.read_sql("SELECT * FROM check_results ORDER BY timestamp DESC LIMIT 100", engine)
        if not checks_df.empty:
            st.dataframe(checks_df, use_container_width=True, hide_index=True)
        else:
            st.info("No check results recorded yet.")
    except Exception as e:
        st.error(f"Error loading check results: {e}")
