# Architecture

## Overview

This solution implements an **Agentic AI** pattern where an LLM (Claude Sonnet 4) autonomously decides which tools to call, generates SQL queries dynamically, and synthesizes results — all without hardcoded queries or predefined dashboards.

## End-to-End Flow

```
  User: "Top 5 customers by exposure?"
    │
    ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ STEP 1: Streamlit sends prompt to AgentCore Runtime via boto3           │
  │                                                                          │
  │ STEP 2: Strands Agent + Claude Sonnet 4 reasons:                        │
  │         "I need to check the schema first"                               │
  │                                                                          │
  │ STEP 3: Agent calls get_schema_info                                      │
  │         → MCP Gateway → Lambda Proxy → Lambda MCP Server → MSSQL        │
  │         ← returns table/column metadata                                  │
  │                                                                          │
  │ STEP 4: Claude generates SQL:                                            │
  │         SELECT TOP 5 full_name, total_exposure_usd                       │
  │         FROM customers ORDER BY total_exposure_usd DESC                  │
  │                                                                          │
  │ STEP 5: Agent calls execute_sql_query                                    │
  │         → MCP Gateway → Lambda Proxy → Lambda MCP Server → MSSQL        │
  │         ← returns 5 rows of results                                      │
  │                                                                          │
  │ STEP 6: Claude formats response with analysis                            │
  └──────────────────────────────────────────────────────────────────────────┘
    │
    ▼
  User sees: formatted answer + execution trace + SQL + timing
```

## System Architecture

```
                            ┌─────────────────────────────────────────────────────────┐
                            │              AI Region (eu-west-1)                       │
                            │                                                         │
  ┌──────────┐   invoke     │  ┌──────────────────┐    prompt    ┌─────────────────┐  │
  │          │─────────────►│  │  AgentCore        │────────────►│  Claude          │  │
  │ Streamlit│   (boto3)    │  │  Runtime          │◄────────────│  Sonnet 4        │  │
  │ Frontend │              │  │  (microVM)        │   response  │  (Bedrock)       │  │
  │ (EC2)    │◄─────────────│  │                   │             └─────────────────┘  │
  └──────────┘   JSON       │  │  ┌─────────────┐ │                                   │
  me-south-1                │  │  │ AgentCore   │ │  tool calls                       │
                            │  │  │ Memory      │ │─────────┐                         │
                            │  │  │ (STM + LTM) │ │         ▼                         │
                            │  │  └─────────────┘ │  ┌──────────────┐                 │
                            │  └──────────────────┘  │ MCP Gateway  │                 │
                            │                        │ (IAM + SigV4)│                 │
                            │                        └──────┬───────┘                 │
                            │                               │                         │
                            │                        ┌──────▼───────┐                 │
                            │                        │ Lambda Proxy │                 │
                            │                        │ (forwarder)  │                 │
                            │                        └──────┬───────┘                 │
                            └───────────────────────────────┼─────────────────────────┘
                                                            │ cross-region invoke
                            ┌───────────────────────────────┼─────────────────────────┐
                            │  Data Region (me-south-1)     │                         │
                            │                        ┌──────▼───────────┐             │
                            │                        │ Lambda MCP Server│             │
                            │                        │ (3 tools)        │             │
                            │                        └──────┬───────────┘             │
                            │                               │ VPC private subnet      │
                            │                        ┌──────▼───────┐                 │
                            │                        │  RDS MSSQL   │                 │
                            │                        │  (5 tables)  │                 │
                            │                        │  1,315 rows  │                 │
                            │                        └──────────────┘                 │
                            └─────────────────────────────────────────────────────────┘
```

## Component Details

### Strands Agent (AgentCore Runtime)

- Runs as a containerized HTTP server on AgentCore Runtime (microVM isolation)
- Uses `strands-agents` SDK with `BedrockModel` for Claude Sonnet 4
- Connects to MCP Gateway via `streamablehttp_client` with SigV4 authentication
- System prompt provides banking context; schema discovery is dynamic

### AgentCore Gateway (MCP Endpoint)

- Exposes 3 MCP tools as a managed endpoint
- IAM authentication (no anonymous access)
- Routes tool calls to the Lambda Proxy
- Tool schemas define input/output contracts

### Lambda MCP Server

- 3 tools:
  - `execute_sql_query` — runs any SELECT query (write operations blocked)
  - `get_schema_info` — returns table/column metadata from INFORMATION_SCHEMA
  - `analyze_blob_data` — extracts VARBINARY content, detects content type, returns preview
- Runs inside VPC private subnets (same as RDS)
- Credentials from Secrets Manager via VPC endpoint

### Lambda Proxy (Cross-Region Bridge)

- Solves: AgentCore Gateway (eu-west-1) can't invoke Lambda in opt-in regions (me-south-1)
- Forwards event payload + client_context (contains tool name) to the MCP Server
- Adds ~200-250ms latency (2-3% of total response time)

### Frontend (Streamlit)

- Chat interface with session management
- 5 tabs: AI Analyst, Architecture, Database, FAQs, Memory
- Sidebar with RM selection and example queries
- Execution Details expander showing tool calls, SQL, results, and timing

## Security Architecture

```
  Internet
      │
      ▼ (restricted to specific IP)
  ┌─────────────────────────────────────────────────────────────┐
  │ Public Subnet                                                │
  │   ┌──────────────────────────────────────────────────────┐  │
  │   │ EC2 (Streamlit)                                       │  │
  │   │ SG: port 8501 from allowed IP only                    │  │
  │   │ IAM Instance Profile → invoke AgentCore Runtime       │  │
  │   └──────────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────────┘
      │ (no direct DB access)
  ┌─────────────────────────────────────────────────────────────┐
  │ Private Subnets                                              │
  │   ┌────────────────────┐    ┌─────────────────────────────┐ │
  │   │ Lambda MCP Server  │    │ VPC Endpoint                │ │
  │   │ SG: outbound only  │    │ (Secrets Manager)           │ │
  │   └────────┬───────────┘    │ No internet transit         │ │
  │            │                └─────────────────────────────┘ │
  │   ┌────────▼───────────┐                                    │
  │   │ RDS MSSQL          │                                    │
  │   │ SG: 1433 from      │                                    │
  │   │     Lambda SG only │                                    │
  │   │ KMS encrypted      │                                    │
  │   └────────────────────┘                                    │
  └─────────────────────────────────────────────────────────────┘
```

| Layer | Implementation |
|-------|---------------|
| API Authentication | IAM auth on AgentCore Gateway (no anonymous) |
| Request Signing | SigV4 on every Gateway request |
| Network Isolation | Lambda + RDS in VPC private subnets |
| Network Controls | Security Groups restrict port 1433 to Lambda SG only |
| Encryption at Rest | KMS encryption on RDS |
| Credential Management | Secrets Manager with VPC endpoint (no internet) |
| Function Policies | Resource policies on all Lambda functions |
| Frontend Access | Security Group restricted to specific IP CIDR |
| SQL Injection Prevention | Blocked write keywords (DROP, DELETE, INSERT, etc.) |
| Data Sovereignty | All data stays in the data region |

## Cross-Region Design

**Why two regions?**
- Data sovereignty: banking data stays in Bahrain (me-south-1)
- Service availability: Bedrock AgentCore only available in select regions
- The proxy bridge adds minimal overhead (~230ms per tool call)

**What crosses the boundary?**
- Only JSON payloads (tool inputs/outputs) cross regions
- Raw VARBINARY blobs are decoded in me-south-1 — only text previews cross
- No customer PII leaves the data region in raw form

## Performance Profile

| Component | Latency | % of Total |
|-----------|---------|------------|
| LLM Reasoning (Claude Sonnet 4) | 3-8s | 85-90% |
| Gateway → Proxy → Lambda → RDS | 350-400ms | 5-8% |
| Response formatting | 1-2s | 10-15% |
| **Total end-to-end** | **5-15s** | **100%** |

## BLOB Data Handling

This is a key differentiator vs BI tools (which skip VARBINARY columns during import):

```
  Agent: "Analyze the GCC Oil & Gas report"
    │
    ▼
  analyze_blob_data(table="research_reports", blob_column="report_content", row_id=1)
    │
    ▼
  Lambda reads raw bytes from MSSQL
    │
    ▼
  Detects content type from magic bytes (%PDF → PDF, PK → Office doc)
    │
    ▼
  Extracts readable text content (up to 2000 chars)
    │
    ▼
  Returns preview → Claude analyzes and summarizes
```
