"""NeoBank — AI Research & Data Analyst Agent — Streamlit Frontend."""
import json
import re
import uuid
import time
import os
import sys
import boto3
import streamlit as st

st.set_page_config(page_title="NeoBank AI Analyst", page_icon="🏦", layout="wide")

# ── Auth gate ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cognito_auth import login_page, logout_button
if not login_page():
    st.stop()

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


def render_architecture():
    """Render the technical architecture page."""

    st.title("🏗️ Technical Architecture")
    st.caption("NeoBank AI Research & Data Analyst — System Design & Components")

    # ── Architecture Diagram (generated with Amazon Nova Canvas) ──
    import os
    diagram_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "architecture_diagram.png")
    if os.path.exists(diagram_path):
        st.image(diagram_path, use_container_width=True)
        st.caption("Architecture diagram generated with Amazon Nova Canvas on Amazon Bedrock")
    else:
        st.info("Architecture diagram not found. Place architecture_diagram.png alongside app.py.")

    # ── Component Details ──
    st.header("Component Details")

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("🗄️ Data Layer (me-south-1 — Bahrain)")
        st.markdown("""
        **RDS SQL Server Express**
        - Engine: SQL Server Express 2022
        - Encryption: AWS KMS (at rest + in transit)
        - Network: Private subnet, no public access
        - Auth: Secrets Manager (rotatable)

        **Database: NeoBank**
        | Table | Records | Purpose |
        |-------|---------|---------|
        | `customers` | 20 | GCC banking clients |
        | `financial_data` | 80 | Quarterly financials |
        | `market_analysis` | 10 | Sector reports |
        | `research_reports` | 5 | PDF blobs (VARBINARY) |
        | `transactions` | 1,200 | Banking transactions |
        """)

        st.subheader("🤖 Lambda MCP Server")
        st.markdown("""
        **3 MCP Tools exposed:**

        `execute_sql_query` — Run read-only SQL
        - Blocks: DROP, DELETE, INSERT, UPDATE, ALTER, TRUNCATE
        - Returns: JSON with rows + row_count

        `get_schema_info` — Discover tables/columns
        - No args → list all tables
        - With table_name → column details + types

        `analyze_blob_data` — Extract VARBINARY content
        - Decodes PDF binary → text preview
        - Returns: content_type, size, preview
        """)

    with c2:
        st.subheader("🧠 AI Layer (eu-west-1 — Ireland)")
        st.markdown("""
        **Strands Agent on AgentCore Runtime**
        - Model: Claude Sonnet 4 (`eu.anthropic.claude-sonnet-4-20250514-v1:0`)
        - Framework: Strands Agents SDK
        - Deployment: AgentCore Runtime (containerized)
        - Auth: IAM (SigV4 signed requests)

        **AgentCore Gateway**
        - Protocol: MCP (Model Context Protocol)
        - Auth: AWS IAM
        - Routes tool calls to Lambda Proxy

        **Lambda Proxy**
        - Bridges eu-west-1 → me-south-1
        - Invokes MCP Server Lambda cross-region
        - Overhead: ~230ms per call (2-3% of total)
        """)

        st.subheader("🔐 Security Architecture")
        st.markdown("""
        | Layer | Mechanism |
        |-------|-----------|
        | Frontend → AgentCore | IAM Instance Profile |
        | AgentCore → Gateway | IAM SigV4 |
        | Gateway → Proxy | IAM Resource Policy |
        | Proxy → MCP Server | IAM Lambda Invoke |
        | MCP Server → RDS | Secrets Manager |
        | RDS Storage | KMS Encryption |
        | Network | VPC + Private Subnets |

        **Zero hardcoded credentials** — all auth via IAM roles and Secrets Manager.
        """)

    # ── Cross-Region Design ──
    st.header("Cross-Region Design")
    cr1, cr2 = st.columns(2)
    with cr1:
        st.markdown("""
        **Why two regions?**
        - 🏦 **me-south-1 (Bahrain)**: Data residency — banking data stays in-region
        - 🧠 **eu-west-1 (Ireland)**: AI models — Claude Sonnet 4 available here

        **Data never leaves Bahrain** — only SQL results (JSON) cross the region boundary.
        VARBINARY blobs are decoded in me-south-1 and only text previews are returned.
        """)
    with cr2:
        st.markdown("""
        **Performance Profile**
        | Hop | Latency |
        |-----|---------|
        | Direct Lambda (me-south-1) | ~125-150ms |
        | Via Proxy (cross-region) | ~360-380ms |
        | LLM Reasoning (Claude) | ~12-18s |
        | **Total E2E** | **~15-22s** |

        LLM reasoning is 85-90% of total time. Cross-region overhead is negligible.
        """)

    # ── How SQL Generation Works ──
    st.header("How SQL Generation Works")
    st.markdown("""
    **100% dynamic** — zero hardcoded queries. The agent:

    1. **Discovers schema** → calls `get_schema_info` to learn tables and columns
    2. **Writes SQL** → Claude generates a SELECT query based on schema + user question
    3. **Executes** → calls `execute_sql_query` with the generated SQL
    4. **Interprets** → Claude reads the results and formulates a natural language answer

    The Lambda MCP Server is a **dumb executor** — it has no knowledge of the questions being asked.
    All intelligence lives in the LLM.
    """)
    st.code("""
    User: "What are the top 5 clients by total assets?"
       ↓
    Agent calls: get_schema_info()           → learns table structure
    Agent calls: get_schema_info("customers") → learns column names
    Agent writes: SELECT TOP 5 customer_name, total_assets
                  FROM customers ORDER BY total_assets DESC
    Agent calls: execute_sql_query(...)       → gets results
    Agent: "Here are the top 5 clients by total assets: ..."
    """, language="text")

    # ── Tech Stack ──
    st.header("Technology Stack")
    t1, t2, t3 = st.columns(3)
    with t1:
        st.markdown("""
        **AWS Services**
        - Amazon Bedrock (Claude Sonnet 4)
        - Bedrock AgentCore Runtime
        - AgentCore Gateway (MCP)
        - AWS Lambda (Python 3.12)
        - Amazon RDS (SQL Server)
        - AWS Secrets Manager
        - AWS KMS
        - Amazon EC2
        """)
    with t2:
        st.markdown("""
        **Frameworks**
        - Strands Agents SDK
        - Model Context Protocol (MCP)
        - Streamlit
        - pymssql (MSSQL driver)
        - boto3 (AWS SDK)
        """)
    with t3:
        st.markdown("""
        **Patterns**
        - Agentic AI (tool-use loop)
        - MCP (standardized tool interface)
        - Cross-region proxy
        - Read-only SQL enforcement
        - VARBINARY blob extraction
        - IAM-everywhere (zero secrets in code)
        """)


def render_chat():
    """Render the AI Analyst chat page."""

    st.title("🏦 NeoBank — AI Research & Data Analyst")
    st.caption("Powered by Amazon Bedrock AgentCore • Strands Agents • Claude Sonnet 4")

    # Chat history in a container
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

    # Process pending or new prompt
    pending = st.session_state.pop("pending_query", None)
    if pending:
        _process_prompt(pending, chat_container)


def _process_prompt(prompt, container=None):
    """Process a user prompt and display response."""
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Inject RM context if selected
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
    st.caption("Copy any query below and paste it into the AI Analyst tab — queries adapt to your selected Relationship Manager")

    def query_card(q, desc, category_color):
        st.markdown(f"""<div style="background:#0f1724;border-left:4px solid {category_color};padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:8px">
        <span style="color:{category_color};font-size:15px;font-family:monospace">{q}</span>
        <div style="color:#8896a8;font-size:13px;margin-top:4px">{desc}</div></div>""", unsafe_allow_html=True)

    rm = st.session_state.get("rm_select", "None (General)")
    if rm != "None (General)":
        st.info(f"🎯 Queries below will automatically filter for **{rm}**'s portfolio when you run them.")

    st.header("👤 My Portfolio (RM-Personalized)")
    st.caption("These queries use your selected RM context — select an RM from the sidebar first")
    query_card("What are my clients?", "Lists all clients assigned to your RM profile with exposure and risk details", "#22d3ee")
    query_card("Show me my high-risk clients", "Filters your portfolio by risk rating = High", "#22d3ee")
    query_card("What is my total exposure across all clients?", "Aggregates total USD exposure for your portfolio", "#22d3ee")
    query_card("Which of my clients have pending KYC?", "Compliance check across your assigned clients", "#22d3ee")
    query_card("Compare my clients' revenue performance this quarter", "Financial data for your clients with quarterly trends", "#22d3ee")

    st.header("📊 Aggregations & Analytics")
    query_card("What's the average revenue by country across all clients?", "GROUP BY with AVG aggregation", "#f59e0b")
    query_card("Show me the top 5 clients by total assets, ranked highest to lowest", "TOP N with ORDER BY DESC", "#f59e0b")
    query_card("Which sector has the highest average net income?", "Sector-level financial analysis", "#f59e0b")
    query_card("Compare total transaction volume by type — deposits vs withdrawals vs transfers", "Transaction type breakdown", "#f59e0b")

    st.header("🔗 Cross-Table Joins")
    query_card("Show me all High risk clients along with their latest financial data", "JOIN customers + financial_data with risk filter", "#a78bfa")
    query_card("Which customers have both transactions over 500,000 and a risk rating of High?", "Multi-table filter with threshold", "#a78bfa")
    query_card("List each client's name, country, total assets, and number of transactions", "3-table join with aggregation", "#a78bfa")

    st.header("📈 Market Intelligence")
    query_card("What are the latest market analysis reports and their sentiment?", "Market analysis table scan", "#34d399")
    query_card("Show me all Bullish market reports for the Oil & Gas sector", "Sentiment + sector filter", "#34d399")
    query_card("Which sectors have a Bearish outlook?", "Negative sentiment detection", "#34d399")

    st.header("📄 BLOB / PDF Extraction")
    st.info("These queries trigger the `analyze_blob_data` tool to extract VARBINARY PDF content from the database — the key differentiator of this solution.")
    query_card("Extract the research report for row 1 in the research_reports table", "Direct blob extraction by row ID", "#f472b6")
    query_card("What research PDFs do we have stored in the database?", "Discovers blob data via schema + query", "#f472b6")
    query_card("Pull the blob data from research_reports for the GCC Oil & Gas sector review", "Natural language blob lookup", "#f472b6")

    st.header("🏢 Executive-Level")
    query_card("Give me a risk dashboard — count of clients by risk rating with their average total assets", "Multi-metric aggregation for risk overview", "#fb923c")
    query_card("Which Bahraini clients have declining net income based on their financial data?", "Trend analysis across financial periods", "#fb923c")
    query_card("Show me a complete profile of Al Baraka Banking Group — all data we have", "Full client 360° view across all tables", "#fb923c")
    query_card("What is the total exposure across all High risk clients in Saudi Arabia?", "Country + risk + financial aggregation", "#fb923c")

    st.divider()
    st.markdown("""
    **💡 Tips:**
    - Select an RM from the sidebar to personalize "My Portfolio" queries
    - Start with portfolio queries, then try analytics, then BLOB extraction for the wow factor
    - The agent generates SQL dynamically — no queries are hardcoded
    - Each query shows execution trace with the actual SQL generated by Claude
    """)


def render_database():
    """Render database schema and sample data page."""
    import pandas as pd

    st.title("🗄️ Database Overview")
    st.caption("NeoBank MSSQL Database — Schema, Relationships & Sample Data")

    st.markdown("""
    ### Business Context

    This database represents a **GCC-focused investment bank's core data platform**, containing client profiles,
    quarterly financial statements, market intelligence, research publications, and transaction records.
    It supports relationship managers, credit analysts, and research teams in making data-driven decisions
    across the Gulf Cooperation Council region — covering Bahrain, Saudi Arabia, UAE, Kuwait, Qatar, and Oman.

    The database includes **VARBINARY blob columns** storing actual PDF research reports, demonstrating
    how the AI agent can extract and analyze unstructured data alongside structured SQL queries.
    """)

    # ── ER Diagram ──
    st.header("Entity Relationships")
    er_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "er_diagram.png")
    if os.path.exists(er_path):
        st.image(er_path, use_container_width=True)
    else:
        st.info("ER diagram not found. Place er_diagram.png alongside app.py.")

    st.markdown("**Foreign Key Relationships:** `financial_data`, `transactions`, and `research_reports` all reference `customers.id`")

    # ── Table Details ──
    st.header("Table Schemas & Sample Data")

    # --- customers ---
    with st.expander("👥 customers — 20 rows | Core banking client records", expanded=True):
        st.markdown("GCC corporate, government, and SME banking clients with KYC status, risk ratings, and exposure tracking.")
        cols_df = pd.DataFrame([
            ("id", "INT", "PK, IDENTITY"),
            ("customer_code", "NVARCHAR(20)", "Unique code (CUST001)"),
            ("full_name", "NVARCHAR(200)", "Client name"),
            ("customer_type", "NVARCHAR(20)", "Individual / Corporate / SME / Government"),
            ("country", "NVARCHAR(50)", "Bahrain, Saudi Arabia, UAE, Kuwait, Qatar, Oman"),
            ("sector", "NVARCHAR(100)", "Oil & Gas, Financial Services, etc."),
            ("risk_rating", "NVARCHAR(10)", "Low / Medium / High / Critical"),
            ("relationship_manager", "NVARCHAR(100)", "Assigned RM"),
            ("onboarding_date", "DATE", "Client onboarding date"),
            ("kyc_status", "NVARCHAR(20)", "Verified / Pending / Expired / Rejected"),
            ("total_exposure_usd", "DECIMAL(18,2)", "Total bank exposure in USD"),
        ], columns=["Column", "Type", "Description"])
        st.dataframe(cols_df, use_container_width=True, hide_index=True)

        st.markdown("**Sample Data:**")
        sample = pd.DataFrame([
            ("CUST001", "Gulf Petrochemical Industries", "Corporate", "Bahrain", "Oil & Gas", "Medium", "$45M"),
            ("CUST002", "Al Baraka Banking Group", "Corporate", "Bahrain", "Financial Services", "Low", "$120M"),
            ("CUST003", "Bahrain Telecommunications", "Corporate", "Bahrain", "Telecom", "Low", "$35M"),
            ("CUST004", "National Oil & Gas Authority", "Government", "Bahrain", "Oil & Gas", "Low", "$200M"),
            ("CUST005", "Aluminum Bahrain (Alba)", "Corporate", "Bahrain", "Manufacturing", "Low", "$85M"),
        ], columns=["Code", "Name", "Type", "Country", "Sector", "Risk", "Exposure"])
        st.dataframe(sample, use_container_width=True, hide_index=True)

    # --- financial_data ---
    with st.expander("📊 financial_data — 80 rows | Quarterly financial statements", expanded=False):
        st.markdown("4 quarters × 20 clients = 80 records. Revenue, net income, assets, liabilities, ratios, and credit ratings.")
        cols_df = pd.DataFrame([
            ("id", "INT", "PK"),
            ("customer_id", "INT", "FK → customers.id"),
            ("fiscal_year", "INT", "2025"),
            ("fiscal_quarter", "NVARCHAR(2)", "Q1 / Q2 / Q3 / Q4"),
            ("revenue_usd", "DECIMAL(18,2)", "Quarterly revenue"),
            ("net_income_usd", "DECIMAL(18,2)", "Net income"),
            ("total_assets_usd", "DECIMAL(18,2)", "Total assets"),
            ("total_liabilities_usd", "DECIMAL(18,2)", "Total liabilities"),
            ("equity_usd", "DECIMAL(18,2)", "Shareholder equity"),
            ("debt_to_equity_ratio", "DECIMAL(8,4)", "D/E ratio"),
            ("current_ratio", "DECIMAL(8,4)", "Liquidity ratio"),
            ("roe_pct", "DECIMAL(8,4)", "Return on equity %"),
            ("credit_rating", "NVARCHAR(10)", "AAA to B-"),
        ], columns=["Column", "Type", "Description"])
        st.dataframe(cols_df, use_container_width=True, hide_index=True)

        sample = pd.DataFrame([
            (1, 2025, "Q1", "$12.5M", "$2.1M", "$180M", "$95M", "A-"),
            (1, 2025, "Q2", "$13.8M", "$2.4M", "$185M", "$97M", "A-"),
            (2, 2025, "Q1", "$45.2M", "$8.7M", "$520M", "$380M", "AA"),
            (3, 2025, "Q1", "$8.9M", "$1.5M", "$95M", "$42M", "BBB+"),
            (4, 2025, "Q1", "$95.0M", "$22.3M", "$1.2B", "$650M", "AA+"),
        ], columns=["Customer ID", "Year", "Quarter", "Revenue", "Net Income", "Assets", "Liabilities", "Rating"])
        st.dataframe(sample, use_container_width=True, hide_index=True)

    # --- market_analysis ---
    with st.expander("📈 market_analysis — 10 rows | Sector-level market intelligence", expanded=False):
        st.markdown("GCC sector analysis covering GDP growth, inflation, interest rates, outlook, and analyst recommendations.")
        cols_df = pd.DataFrame([
            ("id", "INT", "PK"),
            ("sector", "NVARCHAR(100)", "Industry sector"),
            ("region", "NVARCHAR(50)", "GCC"),
            ("analysis_date", "DATE", "Report date"),
            ("gdp_growth_pct", "DECIMAL(8,4)", "GDP growth rate"),
            ("inflation_rate_pct", "DECIMAL(8,4)", "Inflation rate"),
            ("sector_outlook", "NVARCHAR(20)", "Positive / Neutral / Negative / Volatile"),
            ("market_cap_usd_bn", "DECIMAL(18,4)", "Sector market cap in $B"),
            ("analyst_recommendation", "NVARCHAR(200)", "Buy / Hold / Sell guidance"),
            ("key_risks", "NVARCHAR(500)", "Risk factors"),
        ], columns=["Column", "Type", "Description"])
        st.dataframe(cols_df, use_container_width=True, hide_index=True)

        sample = pd.DataFrame([
            ("Oil & Gas", "GCC", "3.2%", "2.1%", "Positive", "$850.5B", "Overweight"),
            ("Financial Services", "GCC", "4.1%", "1.8%", "Positive", "$420.8B", "Buy"),
            ("Real Estate", "GCC", "2.8%", "2.5%", "Neutral", "$310.2B", "Hold"),
            ("Telecommunications", "GCC", "3.5%", "1.9%", "Positive", "$180.6B", "Buy"),
            ("Healthcare", "GCC", "5.2%", "2.0%", "Positive", "$95.3B", "Overweight"),
        ], columns=["Sector", "Region", "GDP Growth", "Inflation", "Outlook", "Market Cap", "Recommendation"])
        st.dataframe(sample, use_container_width=True, hide_index=True)

    # --- research_reports ---
    with st.expander("📄 research_reports — 5 rows | PDF research documents (VARBINARY blobs)", expanded=False):
        st.markdown("Full PDF research reports stored as **VARBINARY(MAX)** binary blobs. The AI agent can extract and analyze these using the `analyze_blob_data` tool.")
        cols_df = pd.DataFrame([
            ("id", "INT", "PK"),
            ("title", "NVARCHAR(300)", "Report title"),
            ("report_type", "NVARCHAR(50)", "Regulatory / Credit / Market / Risk / Annual"),
            ("customer_id", "INT", "FK → customers.id (nullable)"),
            ("sector", "NVARCHAR(100)", "Related sector"),
            ("author", "NVARCHAR(100)", "Report author"),
            ("publish_date", "DATE", "Publication date"),
            ("summary", "NVARCHAR(MAX)", "Executive summary text"),
            ("report_content", "VARBINARY(MAX)", "⚡ PDF binary blob"),
            ("classification", "NVARCHAR(20)", "Public / Internal / Confidential / Restricted"),
        ], columns=["Column", "Type", "Description"])
        st.dataframe(cols_df, use_container_width=True, hide_index=True)

        sample = pd.DataFrame([
            (1, "GCC Oil & Gas Sector Annual Review 2025", "Market", "Oil & Gas", "Confidential"),
            (2, "Credit Risk Assessment — Gulf Petrochemical", "Credit", "Oil & Gas", "Restricted"),
            (3, "Bahrain Regulatory Framework Update Q4 2025", "Regulatory", "Financial Services", "Internal"),
            (4, "Al Baraka Banking Group — Annual Credit Review", "Annual", "Financial Services", "Confidential"),
            (5, "GCC Real Estate Market Outlook 2026", "Market", "Real Estate", "Internal"),
        ], columns=["ID", "Title", "Type", "Sector", "Classification"])
        st.dataframe(sample, use_container_width=True, hide_index=True)

    # --- transactions ---
    with st.expander("💳 transactions — 1,200 rows | Banking transaction records", expanded=False):
        st.markdown("Deposits, withdrawals, transfers, loans, payments, FX trades, and securities trades across all 20 clients. Includes risk flagging.")
        cols_df = pd.DataFrame([
            ("id", "INT", "PK"),
            ("customer_id", "INT", "FK → customers.id"),
            ("transaction_date", "DATETIME2", "Transaction timestamp"),
            ("transaction_type", "NVARCHAR(30)", "Deposit / Withdrawal / Transfer / Loan / Payment / FX / Trade"),
            ("amount_usd", "DECIMAL(18,2)", "Amount in USD"),
            ("currency", "NVARCHAR(3)", "BHD / SAR / AED / USD / KWD / QAR"),
            ("counterparty", "NVARCHAR(200)", "Other party"),
            ("description", "NVARCHAR(500)", "Transaction description"),
            ("status", "NVARCHAR(20)", "Completed / Pending / Failed / Reversed"),
            ("risk_flag", "BIT", "0 = normal, 1 = flagged"),
        ], columns=["Column", "Type", "Description"])
        st.dataframe(cols_df, use_container_width=True, hide_index=True)

        sample = pd.DataFrame([
            ("2025-01-15", "Deposit", "$2,500,000", "BHD", "Gulf Petrochemical", "Completed", "No"),
            ("2025-01-16", "Transfer", "$850,000", "USD", "Al Baraka → Investcorp", "Completed", "No"),
            ("2025-01-18", "Loan", "$15,000,000", "SAR", "Saudi Aramco", "Completed", "No"),
            ("2025-02-01", "FX", "$3,200,000", "AED", "Emirates NBD", "Completed", "Yes"),
            ("2025-02-05", "Withdrawal", "$420,000", "KWD", "Kuwait Finance House", "Pending", "No"),
        ], columns=["Date", "Type", "Amount", "Currency", "Counterparty", "Status", "Risk Flag"])
        st.dataframe(sample, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("""
    **📊 Data Summary:** 5 tables | 1,315 total records | 6 GCC countries | 10 industry sectors | VARBINARY PDF blobs
    """)


def render_memory():
    """Render memory testing page."""

    st.title("🧠 Memory Testing")
    st.caption("Test AgentCore Memory — Short-term (within session) & Long-term (across sessions)")

    st.markdown("""
    This tab lets you test the **AgentCore Memory** feature. The agent remembers context within a session
    and learns preferences across sessions. Follow the guided scenario below to see it in action.
    """)

    # Session controls
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"**Current Session:** `{st.session_state.get('session_id', 'none')}`")
    with col2:
        if st.button("🔄 New Session", key="mem_new_session", use_container_width=True):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.rerun()

    st.divider()

    # ── Guided Test Scenario ──
    st.header("📋 Guided Test Scenario")

    st.subheader("Session 1 — Build Context")
    st.markdown("Run these queries in order in the **💬 AI Analyst** tab:")

    session1 = [
        ("1️⃣ Establish identity", "I'm the relationship manager for Bahrain clients. Show me all my Bahrain customers."),
        ("2️⃣ Express interest", "I'm particularly interested in High risk clients. Which ones should I worry about?"),
        ("3️⃣ Deep dive", "Show me the financial data for Gulf Air since they're High risk"),
        ("4️⃣ Market context", "What's the latest market outlook for the Aviation sector?"),
        ("5️⃣ Set preference", "Remember that I prefer seeing data sorted by exposure amount, highest first"),
    ]

    for label, query in session1:
        st.markdown(f"""<div style="background:#0f1724;border-left:4px solid #22d3ee;padding:10px 14px;border-radius:0 8px 8px 0;margin-bottom:6px">
        <span style="color:#22d3ee;font-size:14px;font-weight:bold">{label}</span><br/>
        <span style="color:#e2e8f0;font-size:14px">{query}</span></div>""", unsafe_allow_html=True)

    st.markdown("")
    st.warning("⚡ After completing Session 1, click **🔄 New Session** above, wait 30 seconds, then proceed to Session 2.")

    st.subheader("Session 2 — Test Memory Recall")
    st.markdown("In the new session, try these queries — the agent should recall context from Session 1:")

    session2 = [
        ("6️⃣ Identity recall", "Show me my clients", "Should recall you're the Bahrain RM and show Bahrain clients sorted by exposure"),
        ("7️⃣ Interest recall", "Any updates on my high risk client?", "Should recall Gulf Air was your concern without you naming it"),
        ("8️⃣ Context chain", "How are they doing financially this quarter?", "Should pull Gulf Air's financials without explicit mention"),
    ]

    for label, query, expected in session2:
        st.markdown(f"""<div style="background:#0f1724;border-left:4px solid #f59e0b;padding:10px 14px;border-radius:0 8px 8px 0;margin-bottom:6px">
        <span style="color:#f59e0b;font-size:14px;font-weight:bold">{label}</span><br/>
        <span style="color:#e2e8f0;font-size:14px">{query}</span><br/>
        <span style="color:#34d399;font-size:12px">✅ Expected: {expected}</span></div>""", unsafe_allow_html=True)

    st.divider()

    # ── Memory Status Dashboard ──
    st.header("📊 Memory Status")

    if st.button("🔍 Check Memory Status", use_container_width=True):
        try:
            mem_client = boto3.client("bedrock-agentcore", region_name=REGION)
            ctrl_client = boto3.client("bedrock-agentcore-control", region_name=REGION)
            MEMORY_ID = "NeoBank_Analyst_Memory-QfXapPAih6"
            ACTOR = "demo_user"

            # Memory config
            mem_info = ctrl_client.get_memory(memoryId=MEMORY_ID)
            mem_data = mem_info.get("memory", {})
            st.success(f"Memory: **{mem_data.get('name', MEMORY_ID)}** | Status: **{mem_data.get('status', 'Unknown')}**")

            # Strategies
            strategies = mem_data.get("strategies", [])
            if strategies:
                strat_data = []
                for s in strategies:
                    strat_data.append({
                        "Name": s.get("name", ""),
                        "Type": s.get("type", ""),
                        "Status": s.get("status", ""),
                        "Namespace": ", ".join(s.get("namespaces", [])),
                    })
                st.dataframe(strat_data, use_container_width=True, hide_index=True)

            # Short-term sessions
            st.subheader("Short-term Memory (Sessions)")
            sessions = mem_client.list_sessions(memoryId=MEMORY_ID, actorId=ACTOR)
            sess_list = sessions.get("sessions", [])
            if sess_list:
                for s in sess_list:
                    sid = s.get("sessionId", "")
                    events = mem_client.list_events(memoryId=MEMORY_ID, sessionId=sid, actorId=ACTOR)
                    count = len(events.get("events", []))
                    st.markdown(f"✅ `{sid}` — **{count} events**")
            else:
                st.info("No sessions found yet. Start a conversation in the AI Analyst tab.")

            # Long-term records
            st.subheader("Long-term Memory (Extracted Records)")
            total_lt = 0
            for ns_label, ns in [("Summaries", f"/summaries/{ACTOR}/"), ("Preferences", f"/preferences/{ACTOR}/"), ("Facts", f"/facts/{ACTOR}/")]:
                recs = mem_client.list_memory_records(memoryId=MEMORY_ID, namespace=ns)
                records = recs.get("memoryRecords", [])
                total_lt += len(records)
                if records:
                    st.markdown(f"✅ **{ns_label}**: {len(records)} records")
                    for r in records[:3]:
                        content = r.get("content", {})
                        text = content.get("text", str(content)[:200])
                        st.code(text[:300], language="text")
                else:
                    st.markdown(f"⏳ **{ns_label}**: 0 records (async extraction pending)")

            if total_lt == 0:
                st.info("Long-term extraction is async and may take several minutes after conversations end. Short-term memory powers the cross-session recall in the demo.")

        except Exception as e:
            st.error(f"Error checking memory: {e}")

    st.divider()

    # ── How It Works ──
    st.header("How AgentCore Memory Works")
    m1, m2 = st.columns(2)
    with m1:
        st.markdown("""
        **Short-term Memory**
        - Stores turn-by-turn events per session
        - Enables multi-turn context within a session
        - Agent recalls previous questions/answers
        - Powered by `ListEvents` / `GetEvent` APIs
        - Immediate — no delay
        """)
    with m2:
        st.markdown("""
        **Long-term Memory**
        - Extracts facts, preferences, summaries
        - Persists across sessions
        - Semantic search for relevant memories
        - 3 strategies: SessionSummarizer, PreferenceLearner, FactExtractor
        - Async extraction (minutes to process)
        """)


# ── Session State ──
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Sidebar (always visible) ──
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
    st.divider()
    logout_button()

# ── Main: Tab Navigation ──
tab_chat, tab_arch, tab_db, tab_queries, tab_memory = st.tabs(["💬 AI Analyst", "🏗️ Architecture", "🗄️ Database", "❓ FAQs", "🧠 Memory"])

with tab_chat:
    render_chat()

with tab_arch:
    render_architecture()

with tab_db:
    render_database()

with tab_queries:
    render_sample_queries()

with tab_memory:
    render_memory()

# ── Chat input pinned at bottom (outside tabs) ──
prompt = st.chat_input("Ask about NeoBank's banking data...")
if prompt:
    _process_prompt(prompt)
