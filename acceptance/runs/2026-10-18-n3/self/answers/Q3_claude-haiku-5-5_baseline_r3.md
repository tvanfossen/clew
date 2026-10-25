The tool detects staleness on three axes, tells the caller through a `staleness` block in each reply, and refreshes the index itself before answering when only the data is stale. The caller's job is mostly to restart the client when the server's code is the problem.

**How it knows.** `db_status` in `clew/mcp_server/state.py` (~L1184–1197) computes three things:
- **data:** `source_changed_files` from `_source_drift`, comparing indexed source files against the database.
- **schema:** `build_version` against `CLEW_BUILD_VERSION`.
- **code:** `code_identity()` in `clew/mcp_server/freshness.py`. It compares a SHA-256 digest of every `.py` file's relative path and content, taken at process start, with one taken now. It hashes content, not mtime, because a `git checkout` or `touch` with identical bytes must not count as drift. An unreadable tree yields "cannot tell", which is treated as no evidence, not as a mismatch.

**What it tells the caller.** `freshness.notices()` turns those into up to three messages, ordered data, schema, code. The list is empty when the tool is current, and `db_status` adds it as `staleness` only when non-empty. Each message names an action:
- **data** (`freshness.py` ~L381): "N indexed source file(s) have changed… Call `index(action='refresh')`", with the measured refresh cost attached.
- **schema:** the direction decides the advice. If the index is older than the server, it says to run `index(action='refresh', force=True)`. If the index is newer than the server, it says a rebuild cannot clear the flag and the client must restart.
- **code** (~L450): the server loaded old logic at launch. Reads are still current, because queries open the database per call. Writes are refused, because a build would run the old logic and could drop layers. Only a client restart clears it.

Every query reply gets `staleness` through `staleness_notices()` (`server.py` ~L1548), and that call never raises.

**What the caller does.**
1. **Data stale:** the server does it. Before each query, `_answering_with_refresh` calls `_auto_refresh` (`server.py` ~L1242). That runs `_data_stale`, which returns False if the code axis is stale, so an auto-refresh never builds from a stale process. If data is stale, `_refresh_stale` takes the per-repo build lock with a bounded wait, re-checks inside the lock so concurrent callers produce one build, and runs `_run_build` with `skip_if_fresh=True`. A failed build is logged and the query still answers from the old index with its notice attached.
2. **Explicit refresh:** `index(action='refresh')` skips the build when the index is already current. `force=True` rebuilds anyway, but it does not bypass the code-axis refusal. `build_or_refresh` checks `stale_code_refusal` first, and the refusal says "Nothing was written."
3. **Code stale:** the caller must restart the MCP client. A rebuild does not help, and the tool tells the caller so.
4. **Schema stale in the newer-index direction:** same answer, restart the client.

**Caveats.** I read the code and the docstrings; I did not run anything, so the behaviour above is what the code says, not something I observed. The sibling `IndexCache` uses the same mtime-prefilter, sha256-authority rule as the code axis. The question's word "index" here means the database, and the code axis is about the server process, not the index.