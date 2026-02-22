# Deployment Guide

Step-by-step guide to deploy the NeoBank AI Research & Data Analyst in your AWS account.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| AWS Account | With Bedrock model access enabled for Claude Sonnet 4 |
| AWS CLI v2 | Configured with admin credentials |
| Python 3.11+ | For agent deployment |
| agentcore CLI | `pip install bedrock-agentcore` |
| Regions | Data region (e.g., me-south-1) + AI region (e.g., eu-west-1) |

> **Note**: Bedrock AgentCore is not available in all regions. Use eu-west-1 or us-east-1 for the AI layer. Your data can stay in any region.

## Configuration

Edit the variables at the top of each deployment script before running:

```bash
# Common variables across all scripts
DATA_REGION="me-south-1"          # Where your data lives
AI_REGION="eu-west-1"             # Where AgentCore/Bedrock runs
ACCOUNT_ID="123456789012"         # Your AWS account ID
VPC_ID="vpc-xxxxx"                # Your VPC
PRIVATE_SUBNETS="subnet-a,subnet-b"  # Private subnets for RDS/Lambda
DB_INSTANCE_ID="neobank-mssql"    # RDS instance identifier
DB_NAME="NeoBank"                 # Database name
SECRET_NAME="neobank/rds-credentials"  # Secrets Manager secret name
```

## Phase 1: RDS MSSQL Setup

Creates the RDS SQL Server instance, security groups, and Secrets Manager secret.

```bash
./infrastructure/01-rds-setup.sh
```

What it creates:
- RDS SQL Server Express instance (db.t3.xlarge) in private subnets
- Security group allowing Lambda access on port 1433
- Secrets Manager secret with DB credentials
- VPC endpoint for Secrets Manager (no internet transit)

**Wait ~10 minutes** for the RDS instance to become available.

## Phase 2: Lambda MCP Server

Deploys the MCP Server Lambda with 3 tools and loads sample data.

```bash
./infrastructure/02-lambda-mcp-server.sh
```

What it creates:
- Lambda function `neobank-mcp-server` in VPC private subnets
- IAM role with Secrets Manager read + VPC access
- Invokes data loader to create database, tables, and seed 1,315 records

## Phase 3: Lambda Proxy (Cross-Region)

Required because AgentCore Gateway can't directly invoke Lambda in opt-in regions.

```bash
./infrastructure/03-lambda-proxy.sh
```

What it creates:
- Lambda function `neobank-mcp-proxy` in the AI region
- Forwards requests from Gateway to MCP Server across regions

## Phase 4: AgentCore Gateway

Sets up the MCP Gateway endpoint that the agent connects to.

```bash
./infrastructure/04-agentcore-gateway.sh
```

What it creates:
- AgentCore Gateway with IAM authentication
- Gateway target with 3 MCP tool schemas
- IAM role for Gateway → Lambda invocation

## Phase 5: Strands Agent

Deploys the AI agent to AgentCore Runtime.

```bash
cd src/agent
# Edit .bedrock_agentcore.yaml with your Gateway URL
agentcore configure
agentcore deploy
```

What it creates:
- ECR repository with agent container image
- AgentCore Runtime endpoint
- Agent with Claude Sonnet 4 + MCP tools

## Phase 6: Frontend

Deploys the Streamlit UI on EC2.

```bash
./infrastructure/06-frontend-deploy.sh
```

What it creates:
- EC2 t3.small instance with Streamlit
- Security group restricted to your IP
- systemd service for auto-restart

## Verification

```bash
# Test the agent directly
agentcore invoke '{"prompt": "What are the top 3 customers by total exposure?"}'

# Access the frontend
open http://<EC2_PUBLIC_IP>:8501
```

## Customization

### Using Your Own Database

1. Update `src/lambda_mcp_server/lambda_function.py` — modify the tool schemas if your tables differ
2. Replace `src/lambda_mcp_server/data_loader.py` with your own data loading script
3. Update the agent's system prompt in `src/agent/agent.py` to describe your schema

### Changing the LLM

Edit `src/agent/agent.py`:
```python
model = BedrockModel(
    model_id="eu.anthropic.claude-sonnet-4-20250514-v1:0",  # Change this
    region_name="eu-west-1",
)
```

### Changing Regions

Update the region variables in each deployment script. The architecture supports any combination of data region + AI region.

## Cleanup

```bash
# Delete in reverse order
aws ec2 terminate-instances --instance-ids <frontend-instance-id>
agentcore delete  # Removes agent runtime
# Delete Gateway via boto3 (no CLI support yet)
aws lambda delete-function --function-name neobank-mcp-proxy --region eu-west-1
aws lambda delete-function --function-name neobank-mcp-server --region me-south-1
aws rds delete-db-instance --db-instance-identifier neobank-mssql --skip-final-snapshot
```
