# Architecture

## Overview

This solution implements an **Agentic AI** pattern where an LLM (Claude Sonnet 4) autonomously decides which tools to call, generates SQL queries dynamically, and synthesizes results — all without hardcoded queries or predefined dashboards.

## End-to-End Flow

```
1. User asks: "Top 5 customers by exposure?"
2. Streamlit → AgentCore Runtime (invoke via boto3)
3. Strands Agent receives prompt
4. Claude Sonnet 4 reasons: "I need to check the schema first"
5. Agent calls get_schema_info → Gateway → Proxy → Lambda → MSSQL
6. Claude sees columns, generates: SELECT TOP 5 full_name, total_exposure_usd FROM customers ORDER BY total_exposure_usd DESC
7. Agent calls execute_sql_query → Gateway → Proxy → Lambda → MSSQL
8. Results return through the chain
9. Claude formats the response with analysis
10. Response streams back to Streamlit UI
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
- Sidebar with example queries
- **Execution Details expander** showing:
  - Tool calls with generated SQL (syntax highlighted)
  - Query results as dataframes
  - Timing breakdown and data flow diagram

## Security Architecture

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

```
Data Region (me-south-1)          AI Region (eu-west-1)
┌─────────────────────┐          ┌─────────────────────┐
│ RDS MSSQL           │◄────────│ Lambda Proxy        │
│ Lambda MCP Server   │          │ AgentCore Gateway   │
│ Secrets Manager     │          │ AgentCore Runtime   │
│ Streamlit Frontend  │          │ Bedrock (Claude)    │
└─────────────────────┘          └─────────────────────┘
```

**Why two regions?**
- Data sovereignty: banking data stays in the data region
- Service availability: Bedrock AgentCore only available in select regions
- The proxy bridge adds minimal overhead (~230ms per tool call)

## Performance Profile

| Component | Latency |
|-----------|---------|
| LLM Reasoning (Claude Sonnet 4) | 3-8s (85-90% of total) |
| Gateway → Proxy → Lambda → RDS | 350-400ms (5-8%) |
| Response formatting | 1-2s (10-15%) |
| **Total end-to-end** | **5-15s** |

## BLOB Data Handling

This is a key differentiator vs BI tools (which skip VARBINARY columns during import):

1. Agent calls `analyze_blob_data(table, blob_column, row_id)`
2. Lambda reads raw bytes from MSSQL
3. Detects content type from magic bytes (`%PDF`, `PK` for Office docs)
4. Extracts readable text content
5. Returns preview (up to 2000 chars) for the agent to analyze
