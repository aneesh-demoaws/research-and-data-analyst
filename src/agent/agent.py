"""NeoBank Agentic AI Research & Data Analyst — Strands Agent for AgentCore Runtime."""
import json
import os
import time
import traceback

import boto3
from httpx_auth_awssigv4 import SigV4Auth
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

GATEWAY_URL = os.environ.get(
    "GATEWAY_URL",
    "https://bankabc-mcp-gateway-5xe20qrqmo.gateway.bedrock-agentcore.eu-west-1.amazonaws.com/mcp",
)
MEMORY_ID = os.environ.get("MEMORY_ID", "NeoBank_Analyst_Memory-QfXapPAih6")
AI_REGION = "eu-west-1"

SYSTEM_PROMPT = """You are NeoBank's Enterprise AI Research & Data Analyst Agent.
You query the NeoBank MSSQL database with GCC banking data.

Tables: customers (20 clients), financial_data (80 quarterly records), market_analysis (10 GCC sectors),
research_reports (5 with VARBINARY blobs), transactions (1200 records).

Workflow: 1) get_schema_info for structure 2) execute_sql_query with SELECT TOP N 3) analyze_blob_data for report_content
Always use TOP clause. Never modify data. Be concise and professional.

You have memory of past conversations. Use what you know about the user to provide better, more personalized responses.
If you recall relevant facts or preferences from previous sessions, incorporate them naturally."""


def _get_auth():
    session = boto3.Session()
    creds = session.get_credentials().get_frozen_credentials()
    return SigV4Auth(
        access_key=creds.access_key, secret_key=creds.secret_key,
        service="bedrock-agentcore", region=AI_REGION, token=creds.token,
    )


def _create_transport(headers=None):
    return streamablehttp_client(GATEWAY_URL, auth=_get_auth())


def handler(event, context=None):
    """AgentCore Runtime HTTP handler."""
    try:
        prompt = event.get("prompt", "")
        session_id = event.get("session_id", "default_session")
        actor_id = event.get("actor_id", "default_user")

        if not prompt:
            body = event.get("body", "{}")
            if isinstance(body, str):
                body = json.loads(body)
            prompt = body.get("prompt", "Hello, what can you help me with?")
            session_id = body.get("session_id", session_id)
            actor_id = body.get("actor_id", actor_id)

        model = BedrockModel(
            model_id="eu.anthropic.claude-sonnet-4-20250514-v1:0",
            region_name=AI_REGION, temperature=0.1, streaming=True,
        )

        memory_config = AgentCoreMemoryConfig(
            memory_id=MEMORY_ID,
            session_id=session_id,
            actor_id=actor_id,
            retrieval=RetrievalConfig(short_term=True, long_term=True),
        )

        mcp_client = MCPClient(_create_transport)

        with mcp_client:
            tools = mcp_client.list_tools_sync()

            with AgentCoreMemorySessionManager(memory_config, region_name=AI_REGION) as session_manager:
                agent = Agent(
                    model=model, tools=tools,
                    system_prompt=SYSTEM_PROMPT,
                    session_manager=session_manager,
                )
                t0 = time.time()
                result = agent(prompt)
                total_time = time.time() - t0

            trace = []
            for msg in agent.messages:
                for block in msg.get("content", []):
                    if isinstance(block, dict):
                        if "toolUse" in block:
                            tu = block["toolUse"]
                            trace.append({"step": "tool_call", "tool": tu.get("name", ""), "input": tu.get("input", {})})
                        elif "toolResult" in block:
                            tr = block["toolResult"]
                            content_text = ""
                            for c in tr.get("content", []):
                                if isinstance(c, dict) and "text" in c:
                                    content_text = c["text"][:500]
                            trace.append({"step": "tool_result", "status": tr.get("status", ""), "output": content_text})

            metrics = result.metrics.get_summary() if hasattr(result, "metrics") else {}

            return {
                "response": str(result),
                "trace": trace,
                "timing": {"total_seconds": round(total_time, 2), "cycles": metrics.get("total_cycles", 0), "duration": round(metrics.get("total_duration", 0), 2)},
                "model": "Claude Sonnet 4",
                "memory": {"id": MEMORY_ID, "session_id": session_id, "actor_id": actor_id},
            }
    except Exception as e:
        traceback.print_exc()
        return {"response": f"Error: {str(e)}", "trace": [], "timing": {}, "model": "Claude Sonnet 4"}


if __name__ == "__main__":
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class AgentHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            try:
                result = handler(body)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())

    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), AgentHandler)
    print(f"Agent server running on port {port}")
    server.serve_forever()
