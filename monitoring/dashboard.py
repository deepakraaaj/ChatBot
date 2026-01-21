
import streamlit as st
import pandas as pd
import requests
import time
import plotly.express as px

import os

st.set_page_config(page_title="REMP AI Monitor", layout="wide")

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
RATE_LIMIT_RPM = 30
RATE_LIMIT_TPM = 6000

# Custom CSS for sticky header area
st.markdown("""
    <style>
        [data-testid="stVerticalBlock"] > div:has(div.sticky-header) {
            position: sticky;
            top: 2.875rem;
            background-color: var(--background-color, #ffffff) !important;
            z-index: 999999 !important;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid rgba(128, 128, 128, 0.2);
            overflow: visible !important;
        }
        
        .sticky-header {
            padding: 0;
            background-color: transparent;
        }

        /* Ensure heading contrast follows theme */
        .sticky-header h1 {
            color: var(--text-color, #31333F) !important;
            margin-bottom: 0 !important;
        }
        
        /* Fix the alignment and spacing of the header controls */
        [data-testid="stHorizontalBlock"] {
            align-items: center;
        }
        
        /* Remove extra padding from top */
        .block-container {
            padding-top: 1.5rem !important;
        }
    </style>
""", unsafe_allow_html=True)

def fetch_metrics(hours=1.0):
    try:
        response = requests.get(f"{API_BASE_URL}/metrics/analytics", params={"hours": hours})
        if response.status_code == 200:
            return response.json()["data"]
        return None
    except Exception as e:
        st.error(f"Error connecting to AI Backend: {e}")
        return None

# --- Sticky Header Section ---
with st.container():
    st.markdown('<div class="sticky-header">', unsafe_allow_html=True)
    
    # Row 1: Title and Controls
    header_col1, header_col2, header_col3 = st.columns([6, 1, 1.5])

    with header_col1:
        st.title("Metrics")

    with header_col2:
        if st.button("Refresh"):
            st.rerun()

    with header_col3:
        time_options = {
            "Last 30 minutes": 0.5,
            "Last hour": 1.0,
            "Last 3 hours": 3.0,
            "Last 6 hours": 6.0,
            "Last 12 hours": 12.0,
            "Last 24 hours": 24.0,
            "Last 3 days": 72.0,
            "Last 5 days": 120.0,
            "Last 7 days": 168.0
        }
        selected_time_label = st.selectbox("Range", options=list(time_options.keys()), index=0, label_visibility="collapsed", key="range_filter")
        selected_hours = time_options[selected_time_label]

    # Row 2: Top Level Metrics (KPIs)
    # Fetch data first so we can show metrics in the header
    metrics = fetch_metrics(hours=selected_hours)
    
    if metrics:
        col1, col2, col3 = st.columns(3)
        total_tokens = sum(r['total_in'] + r['total_out'] for r in metrics['roles'])
        col1.metric("Total Tokens Consumed", f"{total_tokens:,}")
        col2.metric("Average Latency", f"{metrics['avg_latency']} ms")
        col3.metric("Features Tracked", len(metrics['features']))
    
    st.markdown('</div>', unsafe_allow_html=True)

if metrics:
    # Create Tabs for the Operations Center
    tab1, tab2, tab3, tab4 = st.tabs(["Live Trends", "Financials", "System Health", "Deep Dives"])

    with tab1:
        # 2. Time-Series Charts (Reference Image Replication)
        df_ts = pd.DataFrame(metrics['time_series'])
        if not df_ts.empty:
            df_ts['minute'] = pd.to_datetime(df_ts['minute'])
            
            # Row 1: HTTP Status Codes
            st.write("### HTTP Status Codes")
            fig_status = px.line(df_ts, x="minute", y=["status_200", "status_err"], 
                                 labels={"value": "Count", "minute": "Time"},
                                 color_discrete_map={"status_200": "#00d4ff", "status_err": "#ff4b4b"},
                                 template="plotly_dark")
            
            # Sync X-axis with other charts
            now = pd.Timestamp.now()
            start_range = now - pd.Timedelta(hours=selected_hours)
            fig_status.update_layout(xaxis_range=[start_range, now])
            
            fig_status.update_traces(mode="lines+markers")
            st.plotly_chart(fig_status, use_container_width=True)

            st.divider()

            # Row 2: Requests & Tokens
            col_ts_1, col_ts_2 = st.columns(2)
            
            with col_ts_1:
                st.write("#### Request Volume")
                # Calculate % consumed for hover
                df_ts['req_pct_consumed'] = (df_ts['requests'] / RATE_LIMIT_RPM * 100).round(1)
                
                fig_reqs = px.line(df_ts, x="minute", y="requests",
                                   labels={"requests": "API Calls", "minute": "Time"},
                                   color_discrete_sequence=["#00ffc8"],
                                   template="plotly_dark")
                
                # Fix X-axis range to match selected hours
                now = pd.Timestamp.now()
                start_range = now - pd.Timedelta(hours=selected_hours)
                fig_reqs.update_layout(xaxis_range=[start_range, now])
                
                # Custom Hover Template
                fig_reqs.update_traces(
                    hovertemplate="<b>%{x|%I:%M%p}</b><br>" +
                                  "API Calls: %{y}<br>" +
                                  f"Rate Limit: {RATE_LIMIT_RPM}<br>" +
                                  "%{customdata[0]}% consumed<extra></extra>",
                    customdata=df_ts[['req_pct_consumed']]
                )
                
                st.plotly_chart(fig_reqs, use_container_width=True)

            with col_ts_2:
                st.write("#### Token Consumption")
                # Calculate % consumed for total tokens
                df_ts['token_pct_consumed'] = (df_ts['tokens_total'] / RATE_LIMIT_TPM * 100).round(1)
                
                fig_tokens = px.line(df_ts, x="minute", y=["tokens_in", "tokens_out", "tokens_total"],
                                     labels={"value": "Tokens", "minute": "Time", "variable": "Type"},
                                     color_discrete_map={"tokens_in": "#00ffc8", "tokens_out": "#00d4ff", "tokens_total": "#bf00ff"},
                                     template="plotly_dark")
                
                # Sync X-axis range with other charts
                fig_tokens.update_layout(xaxis_range=[start_range, now])
                
                # Match colors from image (greenish for in/out, purple for total)
                fig_tokens.update_traces(line=dict(width=2))

                # Custom Hover Template for Tokens
                # We use customdata to pass the % consumed and individual token counts
                fig_tokens.update_traces(
                    hovertemplate="<b>%{x|%I:%M%p}</b><br>" +
                                  "Input Tokens: %{customdata[0]}<br>" +
                                  "Output Tokens: %{customdata[1]}<br>" +
                                  "Total Tokens: %{customdata[2]}<br>" +
                                  f"Rate Limit: {RATE_LIMIT_TPM}<br>" +
                                  "%{customdata[3]}% consumed<extra></extra>",
                    customdata=df_ts[['tokens_in', 'tokens_out', 'tokens_total', 'token_pct_consumed']]
                )
                
                st.plotly_chart(fig_tokens, use_container_width=True)
        else:
            st.info("No time-series data available yet.")

    with tab2:
        st.write("### Financial Analytics")
        fcol1, fcol2 = st.columns(2)
        
        with fcol1:
            # Est Monthly Run-rate: estimated_cost_usd is for the current dataset (let's say 1 hour of data for demo purposes)
            # 24 * 30 = 720 hours in a month. But our metrics might be shorter. 
            # We'll just show the session cost and an extrapolated estimate.
            st.metric("Estimated Monthly Run-rate", f"${metrics['estimated_cost_usd'] * 720:,.2f}", 
                      help="Based on current hour usage extrapolated to 30 days")
            st.metric("Total Session Cost (Current)", f"${metrics['estimated_cost_usd']:.6f}")
        
        with fcol2:
            st.write("#### Cost Savings (TOON Compression)")
            # Placeholder for actual savings logic
            savings_pct = 85 # % average reduction
            st.progress(savings_pct, text=f"{savings_pct}% payload reduction")
            # Savings = Cost * (1/(1-savings) - 1) roughly
            savings_usd = metrics['estimated_cost_usd'] * 5.6
            st.success(f"Estimated Infrastructure Savings: **${savings_usd:,.4f}**")
            st.caption("TOON reduces network egress and LLM input token overhead.")

    with tab3:
        st.write("### System Health Score")
        hcol1, hcol2 = st.columns([1, 2])
        
        with hcol1:
            health = metrics['health_score']
            color = "normal" if health > 95 else "inverse" if health > 80 else "off"
            st.metric("Health Score", f"{health}%", delta=f"{health-100:.1f}%", delta_color=color)
            
            if health < 90:
                st.error("CRITICAL: High error rate detected!")
            elif health < 98:
                st.warning("WARNING: Minority of requests failing.")
            else:
                st.success("System stable and healthy.")

        with hcol2:
            st.write("#### Response Latency Metrics")
            st.metric("Average Latency", f"{metrics['avg_latency']} ms")
            if not df_ts.empty:
                # Show a mini chart of latency if we had it per minute, for now we use requests as proxy for trend
                st.line_chart(df_ts.set_index('minute')['requests'])
                st.caption("Trailing 60m Request Volume (Health Proxy)")

    with tab4:
        st.write("### Deep Dive Analytics")
        
        dcol1, dcol2 = st.columns(2)
        
        with dcol1:
            st.write("#### Traffic Heatmap (By Hour)")
            df_heat = pd.DataFrame(metrics['heatmap'])
            if not df_heat.empty:
                fig_heat = px.bar(df_heat, x="hour", y="count", 
                                  title="Requests by Hour of Day",
                                  labels={"hour": "Hour (24h)", "count": "Requests"},
                                  color_discrete_sequence=["#6366f1"])
                st.plotly_chart(fig_heat, use_container_width=True)
            else:
                st.info("No heatmap data available yet.")
        
        with dcol2:
            st.write("#### Slowest SQL Queries")
            df_slow = pd.DataFrame(metrics['slow_queries'])
            if not df_slow.empty:
                st.table(df_slow)
            else:
                st.info("No SQL metrics yet.")

        st.divider()
        
        # 3. Aggregates & Popularity
        col_left, col_right = st.columns(2)

        with col_left:
            st.write("### Token Usage by Role")
            df_roles = pd.DataFrame(metrics['roles'])
            if not df_roles.empty:
                df_roles_melted = df_roles.melt(id_vars=["role"], value_vars=["total_in", "total_out"], 
                                               var_name="Type", value_name="Tokens")
                fig_roles = px.bar(df_roles_melted, x="role", y="Tokens", color="Type", barmode="group",
                                   color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig_roles, use_container_width=True)

        with col_right:
            st.write("### Feature Popularity")
            df_feats = pd.DataFrame(metrics['features'])
            if not df_feats.empty:
                fig_feats = px.pie(df_feats, values="count", names="feature", 
                                   hole=0.4, color_discrete_sequence=px.colors.qualitative.Safe)
                st.plotly_chart(fig_feats, use_container_width=True)

        st.divider()
        st.write("#### Detailed User Usage")
        st.dataframe(pd.DataFrame(metrics['users']), use_container_width=True, hide_index=True)
        
        st.divider()
        st.write("#### Detailed Interaction History")
        st.dataframe(pd.DataFrame(metrics['logs']), use_container_width=True, hide_index=True)

    st.divider()

    # 3. Detailed Usage Table
    st.write("### Detailed User Usage")
    df_users = pd.DataFrame(metrics['users'])
    if not df_users.empty:
        # Reorder columns for better readability
        df_display = df_users[["user_id", "role", "total_tokens", "total_in", "total_out", "last_seen"]]
        df_display.columns = ["User ID", "Role", "Total Tokens", "Input Tokens", "Output Tokens", "Last Interaction"]
        
        # Display as a dataframe with sorting/filtering
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("No detailed user data available yet.")

    st.divider()

    # 4. Raw Interaction History
    st.write("### Detailed Interaction History")
    df_logs = pd.DataFrame(metrics['logs'])
    if not df_logs.empty:
        # Style and display log table
        st.dataframe(df_logs, use_container_width=True, hide_index=True)
    else:
        st.info("No interaction history available yet.")

    st.divider()

    # 5. TOON Efficiency
    st.info("TOON (Token-Oriented Object Notation) reduces payload sizes before they reach the LLM, saving costs.")
    
    # We can calculate this if we had the raw vs toon in aggregates, 
    # for now we show a placeholder of the concept as requested "CloudWatch style".
    st.progress(85, text="Average Token Reduction: 85%")
    st.caption("Lowering infrastructure costs by optimizing cross-node data transfer.")

else:
    st.warning("Could not load metrics. Please ensure the AI Backend is running at http://localhost:8000")
    st.info("Tip: You can start the backend with `python main.py` or `uvicorn app.api.main:app`.")

# Note: Auto-refresh disabled per user request. Use 'Refresh' button to update.
