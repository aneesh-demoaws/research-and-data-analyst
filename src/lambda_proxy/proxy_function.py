"""Proxy Lambda in eu-west-1 — forwards MCP tool calls to the MCP server in me-south-1.
Preserves the Gateway context (client_context) which contains the tool name."""
import json
import os
import base64
import boto3

lambda_client = boto3.client("lambda", region_name=os.environ.get("DATA_REGION", "me-south-1"))
TARGET_FUNCTION = os.environ.get("MCP_SERVER_FUNCTION", "neobank-mcp-server")


def handler(event, context):
    # Extract gateway context and forward it
    invoke_kwargs = {
        "FunctionName": TARGET_FUNCTION,
        "InvocationType": "RequestResponse",
        "Payload": json.dumps(event),
    }

    # Forward client context if present (contains bedrockAgentCoreToolName)
    cc = getattr(context, "client_context", None)
    if cc:
        try:
            ctx_data = {"custom": cc.custom or {}, "env": cc.env or {}}
            invoke_kwargs["ClientContext"] = base64.b64encode(json.dumps(ctx_data).encode()).decode()
        except Exception:
            pass

    response = lambda_client.invoke(**invoke_kwargs)
    return json.loads(response["Payload"].read())
