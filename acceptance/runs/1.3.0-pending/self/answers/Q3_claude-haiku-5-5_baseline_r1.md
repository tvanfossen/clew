**Short answer:** clew checks staleness along three independent axes on every status call and on every query reply. It tells the caller what is wrong and which action clears it. For the `data` axis it also refreshes the index itself, so the caller usually does nothing. The `code` and `schema` axes cannot be fixed by a rebuild, so the caller has to restart the MCP client.

I read the code but did not run it, so the behaviour below is from reading, not measurement.

**How it knows**

| Axis | Check | Where |
|---|---|---|
| `data` | Indexed source files (`path` rows with `type=1`) whose mtime is newer than the db's mtime. Mtimes more than 300 s in the future are ignored. An unreadable db counts as "no drift". | `state.py:823` `_source_drift` |
| `schema` | Stamped `build_version` differs from `CLEW_BUILD_VERSION`. | `state.py:1182`, `freshness.py:412` |
| `code` | SHA-256 over the relative paths and bytes of every `.py` in the package, compared with a fingerprint taken at process import. An empty fingerprint means "cannot tell", which counts as a match. | `freshness.py:112`, `:221` |

`db_status` (`state.py:1140`) sets `stale = not exists or schema mismatch or changed > 0`. It then calls `notices()` and adds a `staleness` list only when something is wrong. That list is absent on a current index.

**What it tells the caller**

`staleness` is a list of `{axis, message}`. Each message names the action that clears it:

- **data:** "N indexed source file(s) have changed… Call `index(action='refresh')`", with the measured cost of the last refresh.
- **schema, index older than server:** call `index(action='refresh', force=True)`.
- **schema, index newer than server:** a rebuild cannot clear it. Restart the MCP client.
- **code:** reads are current, but writes are affected. A rebuild cannot clear it. Restart the MCP client.

`staleness_notices()` (`server.py:1548`) puts this list on query replies, so the caller sees it with each answer.

**What the caller does**

1. **Usually nothing for `data`.** Before answering, `_auto_refresh` (`server.py:1242`) rebuilds a data-stale index, but only when the code axis matches the source. A background `keep_current` loop (`server.py:1538`) refreshes every index the session has touched. It runs every 15 s by default; `CLEW_REFRESH_INTERVAL` overrides this and `0` disables it.
2. **Explicit refresh if needed.** `index(action='refresh')` goes through `build_or_refresh` (`server.py:2189`). It refuses first if the process predates its source (`stale_code_refusal`, returning `REFUSED:` and `code` in the reply). It then takes the per-repo build lock and re-checks freshness inside it, so concurrent callers produce one build.
3. **Restart the client** for `code`, or for `schema` when the index is newer than the server.

**Failure behaviour**

- A failed auto-refresh does not turn a good answer into an error. The query answers from the existing index, and the staleness notice is still attached.
- The lock wait is capped at 120 s (`_LOCK_WAIT_SECONDS`), so a stalled build cannot hang the session.
- Unreadable state yields "no evidence" rather than "healthy" for the data axis, and "no warning" for the code axis.

**Caveat from reading the code**

The `data` axis uses mtimes, and the `code` axis uses content hashes. The `code` comment says mtimes fire on `git checkout` even when the bytes are identical, which is why it hashes content. The `data` axis still uses mtimes, so a checkout that touches indexed files can trigger a rebuild with no content change. I did not confirm this against a real checkout.