# SPDX-License-Identifier: MIT
"""The ONE place that imports the MCP SDK's server class, and names the module it needs.

`pyproject` floors the SDK at `mcp>=2,<3`. Generation 1 support is GONE, and this file
used to be the shim that provided it:

    1.x   mcp.server.fastmcp.FastMCP      mcp.server.fastmcp.Context
    2.x   mcp.server.MCPServer            mcp.server.mcpserver.context.Context

## Why the shim was removed rather than kept

Keeping it looked free and was not. `pyproject` had lifted the cap to `mcp>=1.28` on the
strength of the shim, so a fresh `pip install` resolved 2.0.0 — which worked — while
`init_command._check_mcp_sdk` probed `mcp.server.fastmcp` and hard-failed the install. The
advertised path (`pip install` -> `init` -> first MCP call) was therefore broken for every
new user, and the whole test suite stayed green because the check had a test for its FAIL
path and none for its OK path. A warm developer venv holding 1.28.1 passed; nothing else
did.

The lesson is not "shims are bad". It is that supporting two generations means two
environments to keep honest, and this project only ever verified one of them.

## MCP_SERVER_MODULE exists so the doctor cannot drift from the import again

The old check described `mcp.server.fastmcp` as "the server's own import line". That was
true when written and stopped being true the moment this module took over the import — but
the comment kept asserting it, which is what made the staleness invisible. So the module
name is now a constant HERE, exported, and `_check_mcp_sdk` probes THAT. The check and the
import read the same string, which is the only arrangement that cannot rot.

## What is deliberately NOT abstracted

`NotificationOptions` (`mcp.server.lowlevel`) and `stdio_server` (`mcp.server.stdio`) are
imported directly at their use sites. Routing them through here would imply a variability
that no longer exists at all.

@brief Import of the MCP server class and request context, and the module name the doctor probes.
@version 2
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

## `mcp.server.mcpserver.context`, NOT `mcp.server.context` — 2.0 exports a class called
## `Context` from BOTH, and only this one is the injected request context. Picked the other
## one first, by name, and it failed in the least obvious way available: the server
## constructed fine and every tool registered, then `list_tools()` raised
## `PydanticInvalidForJsonSchema` — because a `ctx: Context` parameter annotated with the
## wrong class is not recognised as injectable, so the SDK tried to generate an input schema
## FOR it. `resolve._is_context_annotation` checks `issubclass(annotation, Context)` against
## this class specifically.
##
## Kept from the two-generation era because "the names matched" is exactly the reasoning
## that produced the bug, and a future reader comparing the two modules will find both
## plausible.
from mcp.server.mcpserver.context import Context

## The module whose absence means this interpreter cannot start the server, DERIVED from
## the import above rather than written as a literal. `mcp.server` exists in both
## generations, so naming it would report OK for the one failure worth catching;
## `mcp.server.mcpserver` is 2.x-only and is what the imports above need.
##
## Derived, because a literal is what went stale last time: the doctor named
## `mcp.server.fastmcp` and described it as the server's own import line long after that
## stopped being true. A value computed from the real import cannot say something the
## import contradicts.
MCP_SERVER_MODULE = Context.__module__.rsplit(".", 1)[0]

## The attribute holding the low-level `Server`, which is where the SDK keeps
## `create_initialization_options` and therefore the ONLY route to
## `NotificationOptions(tools_changed=True)`. Private, which is precisely the exposure a
## private attribute implies — resolved here so exactly one module reaches through the SDK's
## privacy. `run_stdio` needs it because `run("stdio")` advertises
## `tools.listChanged=False`, and a client that believes that never re-reads `tools/list`
## when tier-1 appears, which is the entire two-tier design.
LOWLEVEL_ATTR = "_lowlevel_server"


## @brief The low-level Server behind an SDK server instance.
## @param server An MCPServer instance.
## @return The wrapped low-level server object.
## @version 2
## @req REQ-DDB-MCP-001
def lowlevel(server: Any) -> Any:
    """Fails LOUDLY and by name if the attribute is gone: a private hook that vanishes
    should stop the server, not silently drop the capability that makes tier-1
    discoverable.

    @brief Reach the low-level server through its private attribute.
    @return The low-level Server.
    @version 2
    """
    try:
        return getattr(server, LOWLEVEL_ATTR)
    except AttributeError as exc:  # pragma: no cover — a future SDK generation
        raise AttributeError(
            f"the installed mcp SDK has no {LOWLEVEL_ATTR!r}; "
            "clew.mcp_server._sdk needs updating for this version"
        ) from exc


__all__ = ["LOWLEVEL_ATTR", "MCP_SERVER_MODULE", "Context", "MCPServer", "lowlevel"]
