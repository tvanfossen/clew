The reply for `git_argv` (`clew/gitenv.py:89`) is a set of graph edges, not a list of call sites. Here is what it contains and where it misleads.

**What's in it**

- **`callers`**: seven functions that call `git_argv`, each with a file, `edge_class: call`, and `confidence: resolved`. Examples are `run_git` in `clew/guard/git.py`, `tracked_files` in `clew/propose/notindexed.py`, and `test_the_disarmed_key_list_reaches_the_argv`.
- **`callees`**: empty. The body calls `list`, `extend` and reads `GIT_COMMAND_VALUED_KEYS`, none of which are indexed functions.
- **`threads`**: `clew-first-build-`, with `member_count: 72`, reached via `_await_first_build`. This says the function is reachable from that thread. It is not a call edge.
- **`requirements`** and **`covering_tests`**: `REQ-DDB-CONFIG-001` and one test.
- **`liveness`**, `body`, `anchor_mismatch`, and `writes`/`reads`/`overrides`, which are empty here.

**What would make a call-site reading wrong**

1. **No lines or arguments.** Each caller is a function, not a call site. The reply doesn't say which line calls `git_argv`, how often, under what condition, or with what arguments. A caller can call it in a loop, on an error path, or only in tests.
2. **Only one hop.** This is depth 1. Transitive callers, such as whoever calls `run_git`, need `depth ≥ 2` with `direction: back`.
3. **"Resolved" covers only what the parser saw.** Calls through function pointers, dispatch tables, string-named lookups or subprocess-driven paths won't appear as callers. The reply reports `callers_unresolved: 0`, which counts only the edges the index attempted to resolve.
4. **Empty callees don't mean no calls.** The `external_callees` field, which the reply documents as holding calls it couldn't resolve, is absent here. Absent is not the same as empty, and this reply doesn't tell me whether the calls it can't resolve were recorded.
5. **Threads and coverage aren't call edges.** `threads` says where the function can run. `covering_tests` is attached through the shared requirement, so `test_mqtt_dispatch_accepts_an_inline_document_not_only_a_path` appears as covering `git_argv` even though its name suggests it doesn't exercise git argv. Reading "covered by" as "calls" would be wrong.
6. **Name-based identity.** Callers are listed by name. If two functions share a name, the reply carries an `ambiguous` block, and the neighbour rows are then shared across candidates. This reply has no such block, so the seven names resolved to one identity each.

So the reply is reliable for "these seven functions have a resolved static call edge to `git_argv`". It is not a complete or line-accurate list of invocation sites, and it does not establish that any of those paths runs.