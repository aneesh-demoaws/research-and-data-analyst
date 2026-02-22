#!/bin/bash
# Phase 4: AgentCore Gateway
# NOTE: Gateway creation requires boto3 (no CLI support yet)
set -e

AI_REGION="eu-west-1"
ACCOUNT_ID=""  # Your AWS account ID

echo "=== Phase 4: AgentCore Gateway ==="
echo "Gateway creation requires Python/boto3. Running setup script..."

python3 << 'PYEOF'
import boto3, json, os

AI_REGION = os.environ.get("AI_REGION", "eu-west-1")
ACCOUNT_ID = os.environ.get("ACCOUNT_ID", "")

# 1. Create Gateway IAM role
iam = boto3.client("iam")
try:
    iam.create_role(
        RoleName="neobank-agentcore-gateway-role",
        AssumeRolePolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"}, "Action": "sts:AssumeRole"}]
        })
    )
    iam.put_role_policy(
        RoleName="neobank-agentcore-gateway-role",
        PolicyName="invoke-proxy",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "lambda:InvokeFunction",
                          "Resource": f"arn:aws:lambda:{AI_REGION}:{ACCOUNT_ID}:function:neobank-mcp-proxy"}]
        })
    )
    print("Created Gateway IAM role")
except Exception as e:
    print(f"Role may already exist: {e}")

import time; time.sleep(10)

# 2. Create Gateway
client = boto3.client("bedrock-agentcore-control", region_name=AI_REGION)
gw = client.create_gateway(
    name="neobank-mcp-gateway",
    protocolType="MCP",
    authorizerType="AWS_IAM",
    roleArn=f"arn:aws:iam::{ACCOUNT_ID}:role/neobank-agentcore-gateway-role"
)
gw_id = gw["gatewayId"]
print(f"Gateway created: {gw_id}")

# Wait for gateway to be ready
time.sleep(5)

# 3. Create Gateway Target with tool schemas
tool_schemas = [
    {"name": "execute_sql_query", "description": "Execute read-only SQL queries on NeoBank MSSQL database.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "SQL SELECT query"}}, "required": ["query"]}},
    {"name": "get_schema_info", "description": "Get database schema — list tables or columns for a table.",
     "inputSchema": {"type": "object", "properties": {"table_name": {"type": "string", "description": "Table name (omit to list all)"}}}},
    {"name": "analyze_blob_data", "description": "Extract VARBINARY blob content from a table.",
     "inputSchema": {"type": "object", "properties": {"table": {"type": "string"}, "blob_column": {"type": "string"}, "row_id": {"type": "integer"}}, "required": ["table", "blob_column", "row_id"]}},
]

target = client.create_gateway_target(
    gatewayIdentifier=gw_id,
    name="NeoBank-MSSQL-Tools",
    targetConfiguration={"lambdaTargetConfiguration": {
        "lambdaArn": f"arn:aws:lambda:{AI_REGION}:{ACCOUNT_ID}:function:neobank-mcp-proxy"
    }},
    toolSchemas=[{"toolSchema": {"type": "object", "properties": s}} for s in tool_schemas]
)
print(f"Gateway Target: {target['targetId']}")

# 4. Add Lambda permission for Gateway
lam = boto3.client("lambda", region_name=AI_REGION)
lam.add_permission(
    FunctionName="neobank-mcp-proxy",
    StatementId="agentcore-gateway",
    Action="lambda:InvokeFunction",
    Principal="bedrock-agentcore.amazonaws.com",
    SourceArn=f"arn:aws:bedrock-agentcore:{AI_REGION}:{ACCOUNT_ID}:gateway/{gw_id}"
)

gw_url = f"https://{gw_id}.gateway.bedrock-agentcore.{AI_REGION}.amazonaws.com/mcp"
print(f"\nGateway URL: {gw_url}")
print("Save this URL — you'll need it for the agent configuration.")
PYEOF

echo ""
echo "=== Phase 4 Complete ==="
echo "Update src/agent/agent.py GATEWAY_URL with the URL printed above."
