"""
NeoBank MVP — Lambda MCP Server for MSSQL Tools.
Invoked by AgentCore Gateway (eu-west-1) via cross-region Lambda invoke.
Tools: execute_sql_query, get_schema_info, analyze_blob_data
"""
import json
import os
import struct
import boto3
import pymssql


def get_db_connection():
    """Get MSSQL connection using credentials from Secrets Manager."""
    sm = boto3.client("secretsmanager", region_name="me-south-1")
    secret = json.loads(sm.get_secret_value(SecretId=os.environ["SECRET_ARN"])["SecretString"])
    return pymssql.connect(
        server=os.environ["DB_HOST"],
        port=int(secret.get("port", 1433)),
        user=secret["username"],
        password=secret["password"],
        database=os.environ.get("DB_NAME", "BankABC"),
        as_dict=True,
    )


def execute_sql_query(query: str, parameters: dict = None) -> dict:
    """Execute parameterized SQL query on MSSQL read replica."""
    blocked = ["DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE", "INSERT", "UPDATE", "EXEC", "EXECUTE"]
    upper = query.upper().strip()
    for kw in blocked:
        if upper.startswith(kw):
            return {"error": f"Blocked: {kw} statements not allowed. Read-only access."}

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if parameters:
            cursor.execute(query, tuple(parameters.values()))
        else:
            cursor.execute(query)
        rows = cursor.fetchall()
        # Convert non-serializable types
        clean = []
        for row in rows[:500]:  # Limit to 500 rows
            clean_row = {}
            for k, v in row.items():
                if isinstance(v, (bytes, bytearray)):
                    clean_row[k] = f"<BLOB {len(v)} bytes>"
                elif hasattr(v, "isoformat"):
                    clean_row[k] = v.isoformat()
                else:
                    clean_row[k] = v
            clean.append(clean_row)
        return {"row_count": len(rows), "rows": clean, "truncated": len(rows) > 500}
    finally:
        conn.close()


def get_schema_info(database_name: str = None, table_name: str = None) -> dict:
    """Retrieve database schema, tables, columns, and relationships."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if table_name:
            cursor.execute("""
                SELECT c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
                       c.IS_NULLABLE, c.COLUMN_DEFAULT
                FROM INFORMATION_SCHEMA.COLUMNS c
                WHERE c.TABLE_NAME = %s
                ORDER BY c.ORDINAL_POSITION
            """, (table_name,))
            columns = cursor.fetchall()
            # Get primary keys
            cursor.execute("""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE TABLE_NAME = %s AND CONSTRAINT_NAME LIKE 'PK_%'
            """, (table_name,))
            pks = [r["COLUMN_NAME"] for r in cursor.fetchall()]
            return {"table": table_name, "columns": columns, "primary_keys": pks}
        else:
            cursor.execute("""
                SELECT TABLE_NAME, TABLE_TYPE
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """)
            return {"tables": cursor.fetchall()}
    finally:
        conn.close()


def analyze_blob_data(table: str, blob_column: str, row_id: int, id_column: str = "id") -> dict:
    """Extract and analyze unstructured data from blob columns."""
    # Validate table/column names (prevent injection)
    if not all(c.isalnum() or c == "_" for c in table + blob_column + id_column):
        return {"error": "Invalid table/column name"}

    conn = get_db_connection()
    try:
        cursor = conn.cursor(as_dict=False)
        cursor.execute(f"SELECT [{blob_column}] FROM [{table}] WHERE [{id_column}] = %s", (row_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            return {"error": f"No blob data found for {id_column}={row_id}"}

        blob = row[0]
        # Detect content type from magic bytes
        content_type = "unknown"
        preview = ""
        if blob[:4] == b"%PDF":
            content_type = "application/pdf"
            # Extract text between stream markers (simplified)
            text = blob.decode("latin-1", errors="ignore")
            # Find readable text segments
            segments = []
            for chunk in text.split("BT"):
                if "ET" in chunk:
                    segments.append(chunk[:chunk.index("ET")])
            preview = " ".join(segments)[:2000] if segments else text[:2000]
        elif blob[:2] == b"PK":
            content_type = "application/vnd.openxmlformats (docx/xlsx)"
            preview = f"Office document, {len(blob)} bytes"
        else:
            content_type = "application/octet-stream"
            try:
                preview = blob.decode("utf-8")[:2000]
            except UnicodeDecodeError:
                preview = f"Binary data, {len(blob)} bytes, first 100 hex: {blob[:100].hex()}"

        return {
            "row_id": row_id,
            "content_type": content_type,
            "size_bytes": len(blob),
            "preview": preview,
        }
    finally:
        conn.close()


# Tool registry
TOOLS = {
    "execute_sql_query": {
        "fn": execute_sql_query,
        "description": "Execute read-only SQL queries on NeoBank MSSQL database. Returns structured results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL SELECT query to execute"},
                "parameters": {"type": "object", "description": "Query parameters for parameterized queries"},
            },
            "required": ["query"],
        },
    },
    "get_schema_info": {
        "fn": get_schema_info,
        "description": "Get database schema info — list tables or get columns/types for a specific table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database_name": {"type": "string", "description": "Database name (default: NeoBank)"},
                "table_name": {"type": "string", "description": "Table name to get columns for. Omit to list all tables."},
            },
        },
    },
    "analyze_blob_data": {
        "fn": analyze_blob_data,
        "description": "Extract and analyze unstructured data from MSSQL blob/VARBINARY columns (PDFs, documents).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table containing the blob column"},
                "blob_column": {"type": "string", "description": "Name of the VARBINARY/IMAGE column"},
                "row_id": {"type": "integer", "description": "Row ID to extract blob from"},
                "id_column": {"type": "string", "description": "Name of the ID column (default: id)"},
            },
            "required": ["table", "blob_column", "row_id"],
        },
    },
}


def handler(event, context):
    """Lambda handler — processes MCP tool calls from AgentCore Gateway."""
    delimiter = "___"
    tool_name = None

    # Gateway format: tool name in context.client_context.custom
    cc = getattr(context, "client_context", None)
    if cc and hasattr(cc, "custom") and cc.custom:
        raw = cc.custom.get("bedrockAgentCoreToolName", "")
        tool_name = raw[raw.index(delimiter) + len(delimiter):] if delimiter in raw else raw

    # Direct invoke format: tool name in event
    if not tool_name:
        raw = event.get("name") or event.get("toolName") or ""
        tool_name = raw.split(delimiter)[-1] if delimiter in raw else raw

    # Gateway sends flat input properties; direct invoke wraps in "arguments"
    if "name" in event or "toolName" in event:
        arguments = event.get("arguments") or event.get("input") or {}
    else:
        arguments = event

    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    arguments = {k: v for k, v in arguments.items() if k not in ("name", "toolName", "arguments", "input")}

    if tool_name not in TOOLS:
        return {
            "content": [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {tool_name}"})}],
            "isError": True,
        }

    try:
        result = TOOLS[tool_name]["fn"](**arguments)
        return {
            "content": [{"type": "text", "text": json.dumps(result, default=str)}],
            "isError": False,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
            "isError": True,
        }
