# SPDX-License-Identifier: MIT
"""R3 — the MCP server over clew.db (official Python MCP SDK, stdio).

Package name is `mcp_server`, deliberately NOT `mcp`, so it never shadows the
installed SDK. The SDK is a REQUIRED dependency (`mcp>=1.28,<2`), not an extra —
serving the index over MCP is what this tool is for, so an install that cannot
start the server is a broken install rather than a missing opt-in.

@brief Public surface of the clew MCP server (R3).
@version 1
"""

from __future__ import annotations

from .server import (
    DocsDbServer,
    build_server,
    main,
    register_query_tools,
    unregister_query_tools,
)
from .state import Target, TargetRegistry

__all__ = [
    "DocsDbServer",
    "Target",
    "TargetRegistry",
    "build_server",
    "main",
    "register_query_tools",
    "unregister_query_tools",
]
