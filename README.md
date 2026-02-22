# NeoBank — AI Research & Data Analyst

An enterprise Agentic AI system that enables natural language querying of MSSQL banking databases. Built on AWS with Strands Agents, Bedrock AgentCore, and MCP tools.

> **Ask a question in plain English → Agent reasons, discovers schema, generates SQL, executes it, and returns analysis.**

## Architecture

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
                                                            │ cross-region
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

```
  MCP Tools:
  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
  │ get_schema_info  │  │ execute_sql_query │  │ analyze_blob_data│
  │                  │  │                  │  │                  │
  │ Discover tables  │  │ Run read-only    │  │ Extract PDF/BLOB │
  │ & columns        │  │ SELECT queries   │  │ from VARBINARY   │
  └─────────────────┘  └──────────────────┘  └──────────────────┘
```

The agent is fully autonomous — no hardcoded queries or predefined dashboards. Claude Sonnet 4 decides which tools to call, discovers the schema dynamically, generates SQL, and synthesizes results.

## Key Features

- **Natural Language SQL** — Ask questions in plain English; the agent generates and executes SQL dynamically
- **VARBINARY Blob Analysis** — Extract and analyze PDF research reports stored as binary data (something BI tools like QuickSight can't do)
- **RM Personalization** — 4 relationship managers with per-RM portfolio filtering and memory isolation
- **AgentCore Memory** — Short-term + long-term memory with extraction strategies for personalized responses
- **Cross-Region Architecture** — Data stays in Bahrain (me-south-1), AI runs in Ireland (eu-west-1) for data sovereignty
- **Security-First** — IAM auth everywhere, VPC isolation, no secrets in code, IP-restricted frontend

## Components

| Component | Purpose | Region |
|-----------|---------|--------|
| Streamlit Frontend | Chat UI with RM selection | Data region |
| Strands Agent | Autonomous AI reasoning | AI region |
| AgentCore Runtime | Managed agent hosting (microVM) | AI region |
| AgentCore Memory | Conversation memory (STM + LTM) | AI region |
| MCP Gateway | Tool endpoint with IAM auth | AI region |
| Lambda Proxy | Cross-region bridge | AI region |
| Lambda MCP Server | 3 database tools | Data region |
| RDS MSSQL | Banking database (5 tables) | Data region |

## Database

5 tables with 1,315 records of GCC banking data:

| Table | Rows | Description |
|-------|------|-------------|
| `customers` | 20 | Clients across 6 GCC countries |
| `financial_data` | 80 | Quarterly financial records (Q1-Q4 2025) |
| `market_analysis` | 10 | GCC sector analyses |
| `research_reports` | 5 | Reports with VARBINARY PDF blobs |
| `transactions` | 1,200 | Banking transactions |

See [docs/database_schema.md](docs/database_schema.md) for full column definitions.

## Repository Structure

```
├── README.md                          # This file
├── ARCHITECTURE.md                    # Detailed architecture & design decisions
├── DEPLOYMENT.md                      # Step-by-step deployment guide
├── docs/
│   ├── security.md                    # Security posture & IAM roles
│   └── database_schema.md            # Full schema with sample queries
├── infrastructure/
│   ├── 01-rds-setup.sh               # RDS MSSQL + VPC + Secrets Manager
│   ├── 02-lambda-mcp-server.sh       # MCP Server Lambda + data loading
│   ├── 03-lambda-proxy.sh            # Cross-region proxy Lambda
│   ├── 04-agentcore-gateway.sh       # MCP Gateway (Python/boto3)
│   ├── 05-agent-deploy.sh            # Agent deployment via agentcore CLI
│   └── 06-frontend-deploy.sh         # EC2 + Streamlit setup
└── src/
    ├── agent/
    │   ├── agent.py                   # Strands Agent with HTTP server
    │   ├── requirements.txt           # Python dependencies
    │   └── .bedrock_agentcore.yaml    # AgentCore Runtime config (template)
    ├── frontend/
    │   └── app.py                     # Streamlit chat interface
    ├── lambda_mcp_server/
    │   ├── lambda_function.py         # 3 MCP tools (SQL, schema, blob)
    │   └── data_loader.py            # Database creation & sample data
    └── lambda_proxy/
        └── proxy_function.py          # Cross-region Lambda forwarder
```

## Quick Start

### Prerequisites

- AWS account with Bedrock model access (Claude Sonnet 4)
- AWS CLI v2 + Python 3.11+
- `pip install bedrock-agentcore`
- Two regions: a data region + an AI region (where AgentCore is available)

### Deploy

```bash
# 1. Edit variables in each script, then run in order:
./infrastructure/01-rds-setup.sh       # ~10 min (RDS creation)
./infrastructure/02-lambda-mcp-server.sh
./infrastructure/03-lambda-proxy.sh
./infrastructure/04-agentcore-gateway.sh

# 2. Deploy agent
cd src/agent
# Edit agent.py GATEWAY_URL and .bedrock_agentcore.yaml
agentcore configure && agentcore deploy

# 3. Deploy frontend
./infrastructure/06-frontend-deploy.sh
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

## Example Queries

```
"What are the top 5 customers by total exposure?"
"Show me the debt-to-equity ratio trend for Saudi Arabian clients"
"How many transactions were flagged as high risk last quarter?"
"Analyze the GCC Oil & Gas research report"
"Compare financial performance across all GCC countries"
```

## Security

| Layer | Control |
|-------|---------|
| Authentication | IAM + SigV4 on all API calls |
| Network | RDS + Lambda in VPC private subnets |
| Secrets | AWS Secrets Manager via VPC endpoint |
| SQL Safety | Write operations blocked at Lambda level |
| Frontend | Security Group restricted to specific IP |
| Data Sovereignty | Banking data never leaves the data region |

See [docs/security.md](docs/security.md) for the full security posture.

## Performance

| Component | Latency |
|-----------|---------|
| LLM Reasoning | 3-8s (85-90% of total) |
| Tool execution (Gateway → Lambda → RDS) | 350-400ms |
| **Total end-to-end** | **5-15s** |

## License

Internal use only.
