"""NeoBank — AI Research & Data Analyst Agent — Streamlit Frontend."""
import json
import re
import uuid
import time
import os
import boto3
import streamlit as st

st.set_page_config(page_title="NeoBank AI Analyst", page_icon="🏦", layout="wide")

AGENT_ARN = "arn:aws:bedrock-agentcore:eu-west-1:519124228967:runtime/bankabc_analyst-9leseM818c"
REGION = "eu-west-1"
REPORT_BUCKET = "bankabc-mvp-519124228967-me-south-1"
REPORTS = {
    "GCC Oil & Gas Sector Review 2025": "reports/01_GCC_Oil_Gas_Sector_Review_2025.pdf",
    "Credit Risk — Gulf Petrochemical": "reports/02_Credit_Risk_Gulf_Petrochemical.pdf",
    "Bahrain Regulatory Update Q4 2025": "reports/03_Bahrain_Regulatory_Update_Q4_2025.pdf",
    "Al Baraka Annual Credit Review": "reports/04_Al_Baraka_Annual_Credit_Review.pdf",
    "GCC Real Estate Outlook 2026": "reports/05_GCC_Real_Estate_Outlook_2026.pdf",
}


@st.cache_resource
def get_client():
    return boto3.client("bedrock-agentcore", region_name=REGION)


@st.cache_resource
def get_s3():
    return boto3.client("s3", region_name="me-south-1", endpoint_url="https://s3.me-south-1.amazonaws.com")


def get_presigned_url(key, expiry=300):
    return get_s3().generate_presigned_url(
        "get_object", Params={"Bucket": REPORT_BUCKET, "Key": key}, ExpiresIn=expiry
    )


def invoke_agent(prompt, session_id):
    """Invoke agent and return parsed response."""
    client = get_client()
    t0 = time.time()
    response = client.invoke_agent_runtime(
        agentRuntimeArn=AGENT_ARN,
        runtimeSessionId=session_id,
        payload=json.dumps({"prompt": prompt, "session_id": session_id, "actor_id": re.sub(r"[^a-zA-Z0-9_-]", "", st.session_state.get("rm_select", "demo_user").replace(" ", "_").lower())}).encode(),
        qualifier="DEFAULT",
    )
    chunks = []
    for chunk in response.get("response", []):
        chunks.append(chunk.decode("utf-8"))
    wall_time = time.time() - t0
    parsed = json.loads("".join(chunks))
    parsed["wall_time"] = round(wall_time, 2)
    return parsed


def render_trace(data):
    """Render the agent trace in a structured expander."""
    trace = data.get("trace", [])
    timing = data.get("timing", {})
    wall = data.get("wall_time", 0)
    model = data.get("model", "Unknown")

    if not trace and not timing:
        return

    with st.expander("🔍 Agent Execution Details", expanded=False):
        cols = st.columns(4)
        cols[0].metric("Total Time", f"{wall}s")
        cols[1].metric("Agent Cycles", timing.get("cycles", "—"))
        cols[2].metric("Model", model)
        tool_calls = sum(1 for t in trace if t.get("step") == "tool_call")
        cols[3].metric("Tool Calls", tool_calls)

        st.divider()

        step_num = 0
        for item in trace:
            if item["step"] == "tool_call":
                step_num += 1
                tool = item["tool"]
                inp = item.get("input", {})
                icon = {"execute_sql_query": "🗄️", "get_schema_info": "📋", "analyze_blob_data": "📄"}.get(tool, "🔧")
                st.markdown(f"**Step {step_num}: {icon} `{tool}`**")
                if "query" in inp:
                    st.code(inp["query"], language="sql")
                elif "table_name" in inp:
                    st.code(f"Schema lookup: {inp.get('table_name', 'all tables')}", language="text")
                elif "table" in inp and "blob_column" in inp:
                    st.code(f"Blob extract: {inp['table']}.{inp['blob_column']} (row {inp.get('row_id', '?')})", language="text")
                else:
                    st.json(inp)
            elif item["step"] == "tool_result":
                output = item.get("output", "")
                status = item.get("status", "success")
                if status == "error":
                    st.error(f"❌ Error: {output[:300]}")
                else:
                    try:
                        result_data = json.loads(output)
                        if "row_count" in result_data:
                            st.success(f"✅ Returned {result_data['row_count']} rows")
                            if result_data.get("rows") and len(result_data["rows"]) <= 10:
                                st.dataframe(result_data["rows"], use_container_width=True)
                        elif "tables" in result_data:
                            tables = [t.get("TABLE_NAME", t) for t in result_data["tables"]]
                            st.success(f"✅ Found {len(tables)} tables: {', '.join(str(t) for t in tables)}")
                        elif "columns" in result_data:
                            st.success(f"✅ Schema for `{result_data.get('table', '')}`: {len(result_data['columns'])} columns")
                        elif "preview" in result_data:
                            st.success(f"✅ Blob extracted: {result_data.get('content_type', '')} ({result_data.get('size_bytes', 0):,} bytes)")
                            st.text(result_data["preview"][:300] + "..." if len(result_data.get("preview", "")) > 300 else result_data.get("preview", ""))
                        else:
                            st.success("✅ Success")
                            st.json(result_data)
                    except (json.JSONDecodeError, TypeError):
                        st.success(f"✅ {output[:200]}")
                st.markdown("---")

        st.markdown("**🔗 Data Flow**")
        st.code(
            "User → Streamlit (me-south-1) → AgentCore Runtime (eu-west-1)\n"
            "  → Claude Sonnet 4 [reasoning + SQL generation]\n"
            "  → AgentCore Gateway (eu-west-1) → Lambda Proxy (eu-west-1)\n"
            "  → Lambda MCP Server (me-south-1) → RDS MSSQL (me-south-1)\n"
            "  → Response back through chain",
            language="text",
        )


def render_chat():
    """Render the AI Analyst chat page."""

    st.title("🏦 NeoBank — AI Research & Data Analyst")
    st.caption("Powered by Amazon Bedrock AgentCore • Strands Agents • Claude Sonnet 4")

    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg["role"] == "assistant" and "trace_data" in msg:
                    for item in msg["trace_data"].get("trace", []):
                        if item.get("step") == "tool_result" and item.get("status", "success") != "error":
                            try:
                                rd = json.loads(item.get("output", "{}"))
                                if "preview" in rd:
                                    with st.expander(f"📄 Raw Document Content — {rd.get('content_type', '')} ({rd.get('size_bytes', 0):,} bytes)", expanded=False):
                                        st.text_area("", rd["preview"], height=400, key=f"hist_blob_{id(item)}")
                            except (json.JSONDecodeError, TypeError):
                                pass
                    render_trace(msg["trace_data"])

    pending = st.session_state.pop("pending_query", None)
    if pending:
        _process_prompt(pending, chat_container)


def _process_prompt(prompt, container=None):
    """Process a user prompt and display response."""
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    rm = st.session_state.get("rm_select", "None (General)")
    agent_prompt = prompt
    if rm != "None (General)":
        agent_prompt = (
            f"[Context: You are acting for relationship manager '{rm}'. "
            f"The customers table has columns: id, customer_code, full_name, customer_type, country, sector, risk_rating, total_exposure_usd, onboarding_date, kyc_status, relationship_manager. "
            f"Always filter by relationship_manager='{rm}' when the user says 'my clients/customers'.]\n\n{prompt}"
        )

    with st.chat_message("assistant"):
        with st.spinner("⏳ Analyzing..."):
            try:
                data = invoke_agent(agent_prompt, st.session_state.session_id)
                response = data.get("response", "No response")
                st.markdown(response)
                for item in data.get("trace", []):
                    if item.get("step") == "tool_result" and item.get("status", "success") != "error":
                        try:
                            rd = json.loads(item.get("output", "{}"))
                            if "preview" in rd:
                                with st.expander(f"📄 Raw Document Content — {rd.get('content_type', '')} ({rd.get('size_bytes', 0):,} bytes)", expanded=True):
                                    st.text_area("", rd["preview"], height=400, key=f"blob_{id(item)}")
                        except (json.JSONDecodeError, TypeError):
                            pass
                render_trace(data)
                st.session_state.messages.append({"role": "assistant", "content": response, "trace_data": data})
            except Exception as e:
                err = f"Error: {str(e)}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})


def render_sample_queries():
    """Render FAQs page with RM-aware sample queries."""

    st.title("❓ Frequently Asked Questions")
    st.caption("Copy any query below and paste it into the AI Analyst tab")

    def query_card(q, desc, color):
        st.markdown(f"""<div style="background:#0f1724;border-left:4px solid {color};padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:8px">
        <span style="color:{color};font-size:15px;font-family:monospace">{q}</span>
        <div style="color:#8896a8;font-size:13px;margin-top:4px">{desc}</div></div>""", unsafe_allow_html=True)

    rm = st.session_state.get("rm_select", "None (General)")
    if rm != "None (General)":
        st.info(f"🎯 Queries will automatically filter for **{rm}**'s portfolio.")

    st.header("👤 My Portfolio (RM-Personalized)")
    query_card("What are my clients?", "Lists all clients assigned to your RM profile", "#22d3ee")
    query_card("Show me my high-risk clients", "Filters your portfolio by risk rating = High", "#22d3ee")
    query_card("What is my total exposure across all clients?", "Aggregates total USD exposure", "#22d3ee")
    query_card("Which of my clients have pending KYC?", "Compliance check across your clients", "#22d3ee")

    st.header("📊 Aggregations & Analytics")
    query_card("What's the average revenue by country?", "GROUP BY with AVG aggregation", "#f59e0b")
    query_card("Top 5 clients by total assets", "TOP N with ORDER BY DESC", "#f59e0b")
    query_card("Compare transaction volume by type", "Transaction type breakdown", "#f59e0b")

    st.header("🔗 Cross-Table Joins")
    query_card("High risk clients with their latest financial data", "JOIN customers + financial_data", "#a78bfa")
    query_card("Clients with transactions over 500K and High risk", "Multi-table filter", "#a78bfa")

    st.header("📈 Market Intelligence")
    query_card("Latest market analysis reports and sentiment", "Market analysis scan", "#34d399")
    query_card("Sectors with Positive outlook", "Sentiment filter", "#34d399")

    st.header("📄 BLOB / PDF Extraction")
    st.info("These trigger `analyze_blob_data` to extract VARBINARY PDF content.")
    query_card("Extract the research report for row 1", "Direct blob extraction", "#f472b6")
    query_card("What research PDFs do we have?", "Discovers blob data", "#f472b6")

    st.header("🏢 Executive-Level")
    query_card("Risk dashboard — clients by risk rating with average assets", "Multi-metric aggregation", "#fb923c")
    query_card("Complete profile of Al Baraka Banking Group", "Full client 360° view", "#fb923c")


# ── Session State ──
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Sidebar ──
with st.sidebar:
    st.header("About")
    st.markdown("""
    This agent queries the **NeoBank MSSQL database** containing:
    - 👥 **20** GCC banking clients
    - 📊 **80** quarterly financial records
    - 📈 **10** market analysis reports
    - 📄 **5** research reports (with PDF blobs)
    - 💳 **1,200** banking transactions
    """)
    st.divider()
    st.markdown("**👤 Select Relationship Manager:**")
    RM_LIST = ["None (General)", "Ahmed Al-Khalifa", "Fatima Hassan", "Mohammed Al-Dosari", "Sara Al-Mannai"]
    selected_rm = st.selectbox("RM", RM_LIST, label_visibility="collapsed", key="rm_select")
    if selected_rm != "None (General)":
        st.success(f"Acting as: **{selected_rm}**")
    st.divider()
    st.markdown("**📄 Research Reports (BLOB PDFs):**")
    for name, s3_key in REPORTS.items():
        url = get_presigned_url(s3_key)
        st.markdown(f"📄 [{name}]({url})", unsafe_allow_html=False)

    st.divider()
    st.markdown("**Quick queries:**")
    examples = [
        "What are my clients?",
        "Show me my high-risk clients",
        "Top 5 clients by total assets",
        "What sectors have a Bullish outlook?",
        "Extract the research report for row 1",
    ]
    for ex in examples:
        if st.button(ex, key=ex, use_container_width=True):
            st.session_state.pending_query = ex

    st.divider()
    if st.button("🔄 New Session", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

# ── Main: Tab Navigation ──
tab_chat, tab_queries = st.tabs(["💬 AI Analyst", "❓ FAQs"])

with tab_chat:
    render_chat()

with tab_queries:
    render_sample_queries()

# ── Chat input ──
prompt = st.chat_input("Ask about NeoBank's banking data...")
if prompt:
    _process_prompt(prompt)
