#!/bin/bash
# Phase 5: Deploy Strands Agent to AgentCore Runtime
set -e

AI_REGION="eu-west-1"

echo "=== Phase 5: Agent Deployment ==="
echo ""
echo "1. Update src/agent/agent.py with your Gateway URL"
echo "2. Update src/agent/.bedrock_agentcore.yaml with your config"
echo ""

cd src/agent

# Configure and deploy
export AWS_DEFAULT_REGION=$AI_REGION
agentcore configure
agentcore deploy

echo ""
echo "=== Phase 5 Complete ==="
echo "Test with: agentcore invoke '{\"prompt\": \"What tables are available?\"}'"
