from __future__ import annotations

import uuid
from typing import Any

import httpx


async def call_mcp_tool(
    server_url: str,
    tool_name: str,
    arguments: dict,
    headers: dict | None = None,
    timeout_s: int | None = None,
) -> dict:
    if not server_url:
        raise ValueError("MCP server_url is required")
    if not tool_name:
        raise ValueError("MCP tool_name is required")

    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    timeout = httpx.Timeout(timeout_s) if timeout_s else None
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(server_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    if isinstance(data, dict) and data.get("error"):
        message = data["error"].get("message") if isinstance(data["error"], dict) else str(data["error"])
        raise RuntimeError(f"MCP tool error: {message}")

    if not isinstance(data, dict) or "result" not in data:
        raise RuntimeError("MCP tool response missing result")

    result = data.get("result")
    if not isinstance(result, dict):
        return {"result": result}
    return result
