"""Optional remote PayPal MCP bridge.

This keeps MCP credentials server-side. It uses the Streamable HTTP JSON-RPC
shape and deliberately surfaces remote errors rather than fabricating results.
"""
import os
import uuid
import httpx
from fastapi import HTTPException


MCP_URL = os.getenv("PAYPAL_MCP_URL", "https://mcp.sandbox.paypal.com/http")
MCP_TOKEN = os.getenv("PAYPAL_MCP_ACCESS_TOKEN", "")


def status() -> dict:
    return {"configured": bool(MCP_TOKEN), "endpoint": MCP_URL, "transport": "Streamable HTTP JSON-RPC"}


async def rpc(method: str, params: dict | None = None) -> dict:
    if not MCP_TOKEN:
        raise HTTPException(503, "PayPal MCP is not configured. Add PAYPAL_MCP_ACCESS_TOKEN to the backend .env.")
    payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params or {}}
    headers = {"Authorization": f"Bearer {MCP_TOKEN}", "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(MCP_URL, headers=headers, json=payload)
    if response.is_error:
        raise HTTPException(502, "PayPal MCP request failed. Check endpoint, token, and remote-server access.")
    return response.json()
