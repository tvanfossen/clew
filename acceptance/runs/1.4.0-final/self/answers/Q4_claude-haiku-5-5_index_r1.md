The answer for `git_argv` (`clew/gitenv.py:89`) is a list of **enclosing functions that call it**, grouped by file, not a list of call sites. It has six callers:

| File | Caller(s) |
|---|---|
| `clew/guard/main.py` | `_detect_git_version` |
| `clew/guard/tags.py` | `_git_ls_files` |
| `clew/scope.py` | `_gitignored_paths`, `_is_dependency_of_parent` |
| `clew/guard/git.py` | `run_git` |
| `clew/propose/notindexed.py` | `tracked_files` |
| `tests/test_security_surface.py` | `test_the_disarmed_key_list_reaches_the_argv` |

Each caller row carries a name, not a line number, so a function that calls `git_argv` twice appears once. The edges are AST-resolved with `confidence: resolved` and `edge_class: call`. The reply also reports `callers_unresolved: 0`, `context_undecidable: 0` and no `ambiguous` block, which means the index claims it resolved every caller it saw. Those zeros are measurements, so they are present rather than omitted.

What makes it wrong to read as a list of call sites:

1. **It is a set of enclosing functions.** To find the lines, you still open each caller. The index tells you who, not where within them.

2. **It is direct edges only.** `run_git` is itself a wrapper, so `git_argv` is reached transitively through `run_git`, `tracked_files` and so on. The "every git call goes through here" property is not something this one-hop list shows; it needs the `depth` walk (`direction: 'back'`) or the test. Here the source-level test `test_every_git_invocation_disarms_the_inspected_trees_config` is what enforces that no call site builds a bare argv, and it works over source text, not the call graph.

3. **Callers include tests.** The test row sits in the same list as production callers. Filter by file before counting "how many production paths run git."

4. **The `threads` field is not a caller list.** `git_argv` is listed as a member of the `clew-first-build-` thread (`_first_build_worker`, `spawn_confidence: medium`, 72 members). That means the function is reachable from that thread's spawn chain, not that the thread calls it directly. The medium confidence matters.

5. **Callees `[]` means no indexed callees, not "calls nothing."** The body calls `list.extend` and `list` construction, which are not indexed symbols, so they do not appear. Don't read the empty list as a claim that the function has no effects.

6. **Dynamic dispatch and function values are invisible.** A function passed as a value, a call through a dict, or a string-named dispatch will not appear as a caller unless the resolver saw a call edge. The `candidates` and `callers_unresolved` fields are how the index says when it could not decide. Here both are empty or zero, but a nonzero count would make the list incomplete.

7. **The answer is a snapshot.** It reflects the index as built. `anchor_mismatch: false` says the lines still match; a stale index would be reported under `staleness`.

In short, `callers` answers "which indexed functions contain a resolved direct call to this name," and the `0` and empty fields are the index's own confidence signals. To answer "does anything run `git` without the disarm," you combine that with the transitive walk and the source test.