# Implementation Guide — AI Research & Data Analyst

Step-by-step guide to deploy the NeoBank AI Research & Data Analyst in your AWS environment.

## Prerequisites

- AWS account with access to **two regions**:
  - **Data Region** (e.g., `me-south-1`) — RDS, Lambda, Secrets Manager
  - **AI Region** (e.g., `eu-west-1`) — Bedrock, AgentCore Runtime, MCP Gateway
- AWS CLI v2 configured with appropriate credentials
- [Bedrock AgentCore CLI](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-cli.html) installed (`pip install bedrock-agentcore`)
- Bedrock model access enabled for **Claude Sonnet 4** in the AI region
- A VPC with private subnets (for RDS + Lambda) and a public subnet (for EC2 frontend)

## Architecture Overview

```
User → Streamlit (EC2) → AgentCore Runtime (microVM) → Claude Sonnet 4 (Bedrock)
                                    ↓
                              MCP Gateway (IAM + SigV4)
                                    ↓
                              Lambda Proxy (eu-west-1) → Lambda MCP Server (me-south-1) → RDS MSSQL
```

**Why two regions?** Bedrock AgentCore and Claude models may not be available in all regions. The data stays in your preferred region while the AI layer runs where Bedrock is available. A Lambda proxy bridges the two.

---

## Phase 1: Database — RDS MSSQL

**What:** Provision a SQL Server instance and store credentials securely.

**Script:** `infrastructure/01-rds-setup.sh`

### Steps

1. **Edit variables** in the script:
   ```bash
   VPC_ID="vpc-xxxxxxxx"
   PRIVATE_SUBNETS="subnet-aaa,subnet-bbb"
   ```

2. **Run the script:**
   ```bash
   chmod +x infrastructure/01-rds-setup.sh
   ./infrastructure/01-rds-setup.sh
   ```

3. **Wait for RDS to be available** (~10 minutes):
   ```bash
   aws rds wait db-instance-available --db-instance-identifier neobank-mssql --region me-south-1
   ```

4. **Note the RDS endpoint:**
   ```bash
   aws rds describe-db-instances --db-instance-identifier neobank-mssql --region me-south-1 \
     --query 'DBInstances[0].Endpoint.Address' --output text
   ```

### What gets created
| Resource | Purpose |
|----------|---------|
| RDS SQL Server Express (`db.t3.xlarge`) | Banking database — encrypted, private, 7-day backups |
| Security Group (RDS) | Allows port 1433 from Lambda SG only |
| Security Group (Lambda) | Attached to Lambda functions for VPC access |
| Secrets Manager secret | Stores DB username/password (auto-generated) |
| VPC Endpoint | Secrets Manager access from private subnets |

---

## Phase 2: Lambda MCP Server + Data Loading

**What:** Deploy the MCP tool server (3 SQL tools) and load sample banking data.

**Script:** `infrastructure/02-lambda-mcp-server.sh`

### Steps

1. **Edit variables** — add outputs from Phase 1:
   ```bash
   ACCOUNT_ID="123456789012"
   DB_HOST="neobank-mssql.xxxxx.me-south-1.rds.amazonaws.com"
   SECRET_ARN="arn:aws:secretsmanager:me-south-1:123456789012:secret:neobank/rds-credentials-xxxxx"
   LAMBDA_SG="sg-xxxxxxxx"
   PRIVATE_SUBNETS="subnet-aaa,subnet-bbb"
   ```

2. **Run the script:**
   ```bash
   ./infrastructure/02-lambda-mcp-server.sh
   ```

   This packages `pymssql`, deploys two Lambdas, and loads all sample data.

3. **Verify data loaded:**
   ```bash
   aws lambda invoke --function-name neobank-data-loader --region me-south-1 \
     --cli-binary-format raw-in-base64-out \
     --payload '{"action":"verify"}' /dev/stdout
   ```
   Expected: `customers: 20, financial_data: 80, market_analysis: 10, research_reports: 5, transactions: 1200`

### What gets created
| Resource | Purpose |
|----------|---------|
| `neobank-mcp-server` Lambda | 3 MCP tools: `execute_sql_query`, `get_schema_info`, `analyze_blob_data` |
| `neobank-data-loader` Lambda | One-time data loader with sample GCC banking data |
| IAM role `neobank-lambda-mcp-role` | Secrets Manager read + VPC access |

### MCP Tools

| Tool | Description |
|------|-------------|
| `execute_sql_query` | Executes read-only SQL against MSSQL. Blocks INSERT/UPDATE/DELETE. |
| `get_schema_info` | Returns table list or column details for a specific table. |
| `analyze_blob_data` | Extracts content from VARBINARY columns (PDF research reports). |

### Database Schema

| Table | Records | Content |
|-------|---------|---------|
| `customers` | 20 | GCC corporate banking clients with risk ratings, sectors, KYC status |
| `financial_data` | 80 | Quarterly financials — revenue, assets, D/E ratio, credit ratings |
| `market_analysis` | 10 | GCC sector analysis — GDP growth, inflation, outlook |
| `research_reports` | 5 | PDF research reports stored as VARBINARY blobs |
| `transactions` | 1,200 | Banking transactions with risk flags |

---

## Phase 3: Lambda Proxy (Cross-Region Bridge)

**What:** A lightweight Lambda in the AI region that forwards MCP tool calls to the data region.

**Script:** `infrastructure/03-lambda-proxy.sh`

### Why is this needed?
AgentCore Gateway (eu-west-1) can only invoke Lambdas in the same region. The proxy forwards requests to the MCP server in me-south-1, preserving the Gateway context (tool name routing).

### Steps

1. **Edit variables:**
   ```bash
   ACCOUNT_ID="123456789012"
   ```

2. **Run:**
   ```bash
   ./infrastructure/03-lambda-proxy.sh
   ```

### What gets created
| Resource | Purpose |
|----------|---------|
| `neobank-mcp-proxy` Lambda (eu-west-1) | Forwards tool calls to `neobank-mcp-server` (me-south-1) |
| IAM role `neobank-lambda-proxy-role` | Permission to invoke the MCP server cross-region |

---

## Phase 4: AgentCore MCP Gateway

**What:** Create a managed MCP Gateway that exposes the Lambda tools to the agent with IAM authentication.

**Script:** `infrastructure/04-agentcore-gateway.sh`

### Steps

1. **Edit variables:**
   ```bash
   export ACCOUNT_ID="123456789012"
   export AI_REGION="eu-west-1"
   ```

2. **Run:**
   ```bash
   ./infrastructure/04-agentcore-gateway.sh
   ```

3. **Save the Gateway URL** printed at the end — you'll need it for the agent.

### What gets created
| Resource | Purpose |
|----------|---------|
| MCP Gateway | Managed endpoint with IAM + SigV4 auth |
| Gateway Target | Routes tool calls to the proxy Lambda |
| IAM role `neobank-agentcore-gateway-role` | Gateway's permission to invoke the proxy |

---

## Phase 5: Strands Agent on AgentCore Runtime

**What:** Deploy the AI agent (Strands framework) as a containerized microVM on AgentCore Runtime.

**Script:** `infrastructure/05-agent-deploy.sh`

### Steps

1. **Update `mvp/agent/agent.py`** — set your Gateway URL:
   ```python
   GATEWAY_URL = "https://YOUR-GATEWAY-ID.gateway.bedrock-agentcore.eu-west-1.amazonaws.com/mcp"
   ```

2. **Configure AgentCore:**
   ```bash
   cd mvp/agent
   agentcore configure
   ```
   Follow the prompts — select your region, create a new agent, choose container deployment.

3. **Deploy:**
   ```bash
   agentcore deploy
   ```
   This builds a Docker image, pushes to ECR, and deploys to AgentCore Runtime.

4. **Test:**
   ```bash
   agentcore invoke '{"prompt": "What tables are available?"}'
   ```

5. **Note the Agent Runtime ARN** from `.bedrock_agentcore.yaml` — needed for the frontend.

### Agent Components

| Component | Purpose |
|-----------|---------|
| `agent.py` | Strands Agent with system prompt, MCP tool integration, AgentCore Memory |
| `requirements.txt` | Dependencies: strands-agents, bedrock-agentcore, mcp, boto3 |
| `Dockerfile` | Container image with OpenTelemetry instrumentation |
| `.bedrock_agentcore.yaml` | AgentCore deployment configuration |

### Agent Features
- **Model:** Claude Sonnet 4 via Bedrock (streaming)
- **Tools:** 3 MCP tools via Gateway (SQL query, schema info, blob analysis)
- **Memory:** AgentCore Memory with short-term + long-term retrieval — the agent remembers past conversations
- **Observability:** OpenTelemetry traces enabled

---

## Phase 6: Streamlit Frontend

**What:** Deploy the web UI on EC2 with Cognito authentication.

**Script:** `infrastructure/06-frontend-deploy.sh`

### Steps

1. **Create a Cognito User Pool** (if not already done):
   ```bash
   POOL_ID=$(aws cognito-idp create-user-pool --pool-name neobank-demo \
     --auto-verified-attributes email --region me-south-1 \
     --query 'UserPool.Id' --output text)

   CLIENT_ID=$(aws cognito-idp create-user-pool-client --user-pool-id $POOL_ID \
     --client-name neobank-frontend --explicit-auth-flows USER_PASSWORD_AUTH \
     --region me-south-1 --query 'UserPoolClient.ClientId' --output text)

   aws cognito-idp admin-create-user --user-pool-id $POOL_ID \
     --username admin@yourcompany.com --temporary-password TempPass123! \
     --message-action SUPPRESS --region me-south-1
   ```

2. **Update `cognito_auth.py`** with your Pool ID and Client ID.

3. **Edit variables** in the script:
   ```bash
   AGENT_ARN="arn:aws:bedrock-agentcore:eu-west-1:123456789012:runtime/your-agent-id"
   KEY_PAIR="your-key-pair"
   VPC_ID="vpc-xxxxxxxx"
   PUBLIC_SUBNET="subnet-ccc"
   INSTANCE_PROFILE="your-instance-profile"
   ```

4. **Run:**
   ```bash
   ./infrastructure/06-frontend-deploy.sh
   ```

5. **Access** the frontend at `http://<EC2-PUBLIC-IP>:8501`

### Frontend Features

| Tab | Description |
|-----|-------------|
| 💬 AI Agent | Chat interface — ask questions in natural language, see SQL traces |
| 🏗️ Architecture | System architecture diagram and component descriptions |
| 🗄️ Database | Schema explorer with sample data preview |
| ❓ FAQs | Pre-built queries organized by category — click to execute |
| 🧠 Memory | View agent's short-term and long-term memory |

### EC2 Instance Profile Permissions
The EC2 role needs:
```json
{
  "Effect": "Allow",
  "Action": "bedrock-agentcore:InvokeAgentRuntime",
  "Resource": "arn:aws:bedrock-agentcore:eu-west-1:ACCOUNT:runtime/*"
}
```

---

## Optional: CloudFront + Custom Domain

For production-grade access with HTTPS and a custom domain:

1. **ACM Certificate** (us-east-1): Request a wildcard cert for your domain
2. **CloudFront Distribution**: Origin pointing to EC2 IP on port 8501, HTTPS only
3. **Route 53**: CNAME/Alias record pointing to CloudFront
4. **Security Group**: Restrict EC2 ingress to CloudFront prefix list only

---

## Optional: Research Report PDFs (BLOB Data)

The database includes 5 research reports stored as VARBINARY blobs. To generate custom PDFs:

```bash
cd mvp/sample_blob_data
pip install reportlab
python generate_pdfs.py
```

Then upload to the database via the data loader's `load_reports` action.

---

## Verification Checklist

After completing all phases, verify end-to-end:

| Check | Command |
|-------|---------|
| RDS accessible | Data loader `verify` action returns row counts |
| MCP tools work | `agentcore invoke '{"prompt": "List all tables"}'` |
| Agent responds | `agentcore invoke '{"prompt": "Show top 5 clients by total assets"}'` |
| Memory works | Ask a question, then ask "What did I just ask you?" |
| Frontend loads | Open browser to EC2 IP:8501, login, ask a question |
| BLOB extraction | Ask "Extract the research report for row 1" |

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Lambda timeout | Can't reach RDS | Check Lambda SG → RDS SG ingress on port 1433 |
| `AccessDeniedException` on invoke | Missing IAM permissions | Verify EC2 role has `bedrock-agentcore:InvokeAgentRuntime` |
| Gateway 403 | SigV4 auth failure | Ensure agent's execution role can access the Gateway |
| Agent can't find tools | Gateway target misconfigured | Verify tool schemas match Lambda handler's TOOLS registry |
| BLOB returns empty | PDF not loaded | Re-run data loader with `load_reports` action |
| Cross-region timeout | Proxy Lambda timeout too low | Increase proxy timeout to 60s |

---

## Cost Estimate

| Resource | Approximate Monthly Cost |
|----------|------------------------|
| RDS SQL Server Express (db.t3.xlarge) | ~$150 |
| Lambda (MCP Server + Proxy + Data Loader) | < $5 |
| AgentCore Runtime (microVM) | Pay-per-invocation |
| Bedrock Claude Sonnet 4 | ~$3/1K input tokens, ~$15/1K output tokens |
| EC2 (t3.small frontend) | ~$15 |
| Secrets Manager | ~$0.40/secret/month |
| **Total (light demo usage)** | **~$175 + Bedrock usage** |

---

## File Reference

```
mvp/
├── agent/
│   ├── agent.py                      # Strands Agent — system prompt, MCP tools, memory
│   ├── requirements.txt              # Python dependencies
│   ├── .bedrock_agentcore.yaml       # AgentCore deployment config
│   └── .bedrock_agentcore/
│       └── <agent_name>/Dockerfile   # Container image definition
├── frontend/
│   ├── app.py                        # Streamlit UI — 5 tabs, Cognito auth, agent invocation
│   ├── cognito_auth.py               # Shared authentication module
│   ├── architecture_diagram.png      # Architecture diagram for the UI
│   └── er_diagram.png                # ER diagram for the Database tab
├── lambda_mcp_server/
│   ├── lambda_function.py            # MCP Server — 3 tools (SQL, schema, blob)
│   └── data_loader.py                # One-time data loader — creates DB + loads sample data
├── lambda_proxy/
│   └── proxy_function.py             # Cross-region forwarder (eu-west-1 → me-south-1)
└── sample_blob_data/
    ├── generate_pdfs.py              # Script to generate sample research report PDFs
    └── *.pdf                         # 5 sample research reports
infrastructure/
├── 01-rds-setup.sh                   # Phase 1: RDS + networking
├── 02-lambda-mcp-server.sh           # Phase 2: MCP tools + data loading
├── 03-lambda-proxy.sh                # Phase 3: Cross-region proxy
├── 04-agentcore-gateway.sh           # Phase 4: MCP Gateway
├── 05-agent-deploy.sh                # Phase 5: Agent deployment
└── 06-frontend-deploy.sh             # Phase 6: Frontend EC2
```
