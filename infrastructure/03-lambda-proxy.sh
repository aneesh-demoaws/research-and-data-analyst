#!/bin/bash
# Phase 3: Lambda Proxy (Cross-Region Bridge)
set -e

AI_REGION="eu-west-1"
DATA_REGION="me-south-1"
ACCOUNT_ID=""  # Your AWS account ID

echo "=== Phase 3: Lambda Proxy ==="

# 1. Create proxy role
aws iam create-role \
  --role-name neobank-lambda-proxy-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy --role-name neobank-lambda-proxy-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam put-role-policy --role-name neobank-lambda-proxy-role \
  --policy-name invoke-mcp \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"lambda:InvokeFunction\",\"Resource\":\"arn:aws:lambda:$DATA_REGION:$ACCOUNT_ID:function:neobank-mcp-server\"}]}"

sleep 10

# 2. Package and deploy
cd src/lambda_proxy
zip proxy_function.zip proxy_function.py
cd ../..

aws lambda create-function \
  --function-name neobank-mcp-proxy \
  --runtime python3.11 \
  --handler proxy_function.handler \
  --role arn:aws:iam::${ACCOUNT_ID}:role/neobank-lambda-proxy-role \
  --zip-file fileb://src/lambda_proxy/proxy_function.zip \
  --timeout 60 --memory-size 256 \
  --environment "Variables={TARGET_FUNCTION=arn:aws:lambda:$DATA_REGION:$ACCOUNT_ID:function:neobank-mcp-server}" \
  --region $AI_REGION

echo ""
echo "=== Phase 3 Complete ==="
echo "Proxy Lambda: neobank-mcp-proxy ($AI_REGION)"
