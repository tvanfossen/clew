---
description: Open this repository's clew wiki — live on the hub when the MCP server runs it, else built and opened as files
---

Run, from the repository root:

```bash
uvx --from "clew-trace[wiki]==2.2.0" clew wiki open --repo-root "$CLAUDE_PROJECT_DIR"
```

It prints the URL it opened. When the clew MCP server runs with `CLEW_WIKI=1` the wiki is served
live by that server, rebuilt as the index refreshes. Otherwise the site is built beside the index
and opened as files, which needs no server. Tell the person the URL. If the build fails, show its
message as it is.
