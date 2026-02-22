#!/bin/bash
# Phase 2: Lambda MCP Server + Data Loading
set -e

DATA_REGION="me-south-1"
ACCOUNT_ID=""       # Your AWS account ID
DB_HOST=""          # RDS endpoint (from Phase 1)
SECRET_ARN=""       # Secrets Manager ARN (from Phase 1)
LAMBDA_SG=""        # Lambda SG (from Phase 1)
PRIVATE_SUBNETS=""  # Comma-separated

echo "=== Phase 2: Lambda MCP Server ==="

# 1. Create IAM role
echo "Creating Lambda execution role..."
aws iam create-role \
  --role-name neobank-lambda-mcp-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy --role-name neobank-lambda-mcp-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole

aws iam put-role-policy --role-name neobank-lambda-mcp-role \
  --policy-name secrets-read \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"secretsmanager:GetSecretValue\"],\"Resource\":\"$SECRET_ARN\"}]}"

echo "Waiting for role propagation..."
sleep 10

# 2. Package Lambda (requires pymssql layer or package)
echo "Packaging Lambda..."
cd src/lambda_mcp_server
pip install pymssql -t package/
cd package && zip -r ../lambda_mcp_server.zip . && cd ..
zip lambda_mcp_server.zip lambda_function.py
cd ../..

# 3. Deploy MCP Server Lambda
echo "Deploying MCP Server Lambda..."
aws lambda create-function \
  --function-name neobank-mcp-server \
  --runtime python3.11 \
  --handler lambda_function.handler \
  --role arn:aws:iam::${ACCOUNT_ID}:role/neobank-lambda-mcp-role \
  --zip-file fileb://src/lambda_mcp_server/lambda_mcp_server.zip \
  --timeout 60 --memory-size 512 \
  --vpc-config SubnetIds=$PRIVATE_SUBNETS,SecurityGroupIds=$LAMBDA_SG \
  --environment "Variables={DB_HOST=$DB_HOST,SECRET_ARN=$SECRET_ARN,DB_NAME=NeoBank}" \
  --region $DATA_REGION

# 4. Deploy Data Loader Lambda
echo "Deploying Data Loader Lambda..."
cd src/lambda_mcp_server
cp data_loader.py package/lambda_function_loader.py
cd package && zip -r ../data_loader.zip . && cd ..
zip data_loader.zip data_loader.py
cd ../..

aws lambda create-function \
  --function-name neobank-data-loader \
  --runtime python3.11 \
  --handler data_loader.handler \
  --role arn:aws:iam::${ACCOUNT_ID}:role/neobank-lambda-mcp-role \
  --zip-file fileb://src/lambda_mcp_server/data_loader.zip \
  --timeout 120 --memory-size 512 \
  --vpc-config SubnetIds=$PRIVATE_SUBNETS,SecurityGroupIds=$LAMBDA_SG \
  --environment "Variables={DB_HOST=$DB_HOST,SECRET_ARN=$SECRET_ARN}" \
  --region $DATA_REGION

# 5. Load sample data
echo "Loading sample data..."
for action in create_db create_tables load_customers load_financial load_market load_reports load_transactions verify; do
  echo "  Running: $action"
  aws lambda invoke \
    --function-name neobank-data-loader \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"action\":\"$action\"}" \
    --region $DATA_REGION \
    /tmp/loader_result.json > /dev/null
  cat /tmp/loader_result.json
  echo ""
done

echo ""
echo "=== Phase 2 Complete ==="
echo "MCP Server: neobank-mcp-server"
echo "Data Loader: neobank-data-loader"
