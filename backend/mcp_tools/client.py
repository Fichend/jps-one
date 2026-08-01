"""Minimal MCP client utilities for JPS One managed MCP servers.

The implementation intentionally stays small: JPS One owns routing and safety,
while each external MCP server remains a replaceable tool endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

Transport = Literal["stdio", "streamable_http"]
StdioMessageFormat = Literal["framed", "json_lines"]


class MCPClientError(RuntimeError):
    """Raised when an MCP server cannot be reached or returns an error."""


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: Transport = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 60
    stdio_message_format: StdioMessageFormat = "framed"


def split_args(raw: str) -> list[str]:
    """Parse comma/newline separated command args from settings."""
    if not raw:
        return []
    parts: list[str] = []
    for chunk in raw.replace("\n", ",").split(","):
        value = chunk.strip()
        if value:
            parts.append(value)
    return parts


def extract_text_content(result: dict[str, Any]) -> str:
    """Return concatenated text payload from a standard MCP tool result."""
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def parse_jsonish(value: Any) -> Any:
    """Best-effort JSON extraction for MCP text responses."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start_candidates = [idx for idx in (text.find("{"), text.find("[")) if idx >= 0]
    if not start_candidates:
        return None
    start = min(start_candidates)
    end = max(text.rfind("}"), text.rfind("]"))
    if end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


class MCPToolClient:
    """Call MCP tools through stdio or streamable HTTP."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.config.transport == "streamable_http":
            return await self._call_http(tool_name, arguments)
        return await self._call_stdio(tool_name, arguments)

    async def _call_http(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.config.url:
            raise MCPClientError(f"{self.config.name} MCP URL is not configured")
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            **self.config.headers,
        }
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds, follow_redirects=True) as client:
            response = await client.post(self.config.url, json=payload, headers=headers)
            response.raise_for_status()
        body = response.text.strip()
        data = _parse_sse_json(body) if body.startswith("event:") or body.startswith("data:") else response.json()
        if isinstance(data, dict) and data.get("error"):
            raise MCPClientError(f"{self.config.name} MCP error: {data['error']}")
        result = data.get("result") if isinstance(data, dict) else None
        if not isinstance(result, dict):
            raise MCPClientError(f"{self.config.name} MCP returned an invalid response")
        return result

    async def _call_stdio(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.config.command:
            raise MCPClientError(f"{self.config.name} MCP command is not configured")
        env = {**os.environ, **{k: v for k, v in self.config.env.items() if v is not None}}
        proc = await asyncio.create_subprocess_exec(
            self.config.command,
            *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            await self._send(proc, "initialize", {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "jps-one", "version": "0.1.0"},
            })
            await self._read_response(proc)
            await self._send_notification(proc, "notifications/initialized", {})
            await self._send(proc, "tools/call", {"name": tool_name, "arguments": arguments})
            result = await self._read_response(proc)
            if result.get("error"):
                raise MCPClientError(f"{self.config.name} MCP error: {result['error']}")
            payload = result.get("result")
            if not isinstance(payload, dict):
                raise MCPClientError(f"{self.config.name} MCP returned an invalid response")
            return payload
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()

    async def _send(self, proc: asyncio.subprocess.Process, method: str, params: dict[str, Any]) -> None:
        msg = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}
        await self._write_line(proc, msg)

    async def _send_notification(self, proc: asyncio.subprocess.Process, method: str, params: dict[str, Any]) -> None:
        await self._write_line(proc, {"jsonrpc": "2.0", "method": method, "params": params})

    async def _write_line(self, proc: asyncio.subprocess.Process, msg: dict[str, Any]) -> None:
        if proc.stdin is None:
            raise MCPClientError(f"{self.config.name} MCP stdin is unavailable")
        if self.config.stdio_message_format == "json_lines":
            proc.stdin.write((json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8"))
            await proc.stdin.drain()
            return
        body = json.dumps(msg, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        proc.stdin.write(header + body)
        await proc.stdin.drain()

    async def _read_response(self, proc: asyncio.subprocess.Process) -> dict[str, Any]:
        if proc.stdout is None:
            raise MCPClientError(f"{self.config.name} MCP stdout is unavailable")

        async def _read() -> dict[str, Any]:
            while True:
                text = await self._read_framed_or_line(proc)
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    logger.debug("[%s MCP] skipping non-json stdout: %s", self.config.name, text[:200])
                    continue
                if "id" in data:
                    return data

        return await asyncio.wait_for(_read(), timeout=self.config.timeout_seconds)

    async def _read_framed_or_line(self, proc: asyncio.subprocess.Process) -> str:
        if proc.stdout is None:
            raise MCPClientError(f"{self.config.name} MCP stdout is unavailable")
        line = await proc.stdout.readline()
        if not line:
            stderr = ""
            if proc.stderr is not None:
                try:
                    stderr = (await proc.stderr.read()).decode("utf-8", errors="replace")
                except Exception:
                    stderr = ""
            raise MCPClientError(f"{self.config.name} MCP exited before response. {stderr}".strip())

        header_line = line.decode("utf-8", errors="replace").strip()
        if not header_line:
            return await self._read_framed_or_line(proc)
        if self.config.stdio_message_format == "json_lines":
            return header_line
        if not header_line.lower().startswith("content-length:"):
            return header_line

        try:
            content_length = int(header_line.split(":", 1)[1].strip())
        except ValueError as exc:
            raise MCPClientError(f"{self.config.name} MCP sent invalid Content-Length") from exc

        while True:
            header = await proc.stdout.readline()
            if header in {b"\r\n", b"\n", b""}:
                break
        body = await proc.stdout.readexactly(content_length)
        return body.decode("utf-8", errors="replace").strip()


def _parse_sse_json(body: str) -> dict[str, Any]:
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if data and data != "[DONE]":
            return json.loads(data)
    raise MCPClientError("MCP streamable HTTP response did not contain JSON data")
