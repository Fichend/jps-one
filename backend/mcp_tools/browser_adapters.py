"""Internal MCP browser-channel configuration for JPS One.

Playwright and Chrome MCP are intentionally not exposed in the Settings page:
they do not need paid API keys, and Chrome MCP may depend on a local extension
or user browser session. Backend workflows can import these helpers when a
human-approved public-page review step is added.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings
from mcp_tools.client import MCPServerConfig, split_args


@dataclass(frozen=True)
class BrowserMCPChannel:
    name: str
    enabled: bool
    purpose: str
    config: MCPServerConfig
    manual_only: bool = False


def build_playwright_channel(settings: Settings) -> BrowserMCPChannel:
    args = split_args(settings.playwright_mcp_args)
    if settings.playwright_mcp_user_data_dir:
        args.extend(["--user-data-dir", settings.playwright_mcp_user_data_dir])
    return BrowserMCPChannel(
        name="playwright",
        enabled=settings.playwright_mcp_enabled,
        purpose="Structured public webpage review, difficult page reading, PDF/devtools-assisted verification.",
        config=MCPServerConfig(
            name="playwright",
            transport="stdio",
            command=settings.playwright_mcp_command,
            args=args,
            timeout_seconds=settings.playwright_mcp_timeout_seconds,
        ),
    )


def build_chrome_channel(settings: Settings) -> BrowserMCPChannel:
    return BrowserMCPChannel(
        name="chrome",
        enabled=settings.chrome_mcp_enabled,
        purpose="Manual/user-session assisted Chrome review through the local Chrome MCP bridge.",
        manual_only=settings.chrome_mcp_manual_only,
        config=MCPServerConfig(
            name="chrome",
            transport="streamable_http",
            url=settings.chrome_mcp_url,
            timeout_seconds=settings.chrome_mcp_timeout_seconds,
        ),
    )


def list_browser_channels(settings: Settings) -> list[BrowserMCPChannel]:
    return [build_playwright_channel(settings), build_chrome_channel(settings)]
