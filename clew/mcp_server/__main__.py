# SPDX-License-Identifier: MIT
"""`python -m clew.mcp_server` — run the R3 MCP server over stdio.

@brief Module entry point for the clew MCP server.
@version 1
"""

from __future__ import annotations

from .server import main

if __name__ == "__main__":
    main()
