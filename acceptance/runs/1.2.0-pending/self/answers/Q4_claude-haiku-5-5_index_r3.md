**What the answer contains.** `dossier` on `git_argv` (clew/gitenv.py:89) returned seven direct callers, each marked `source: ast`, `confidence: resolved`, `edge_class: call`. Six are production functions (`_detect_git_version`, `_git_ls_files`, `_gitignored_paths`, `_is_dependency_of_parent`, `run_git`, `tracked_files`). The seventh is a test, `test_the_disarmed_key_list_reaches_the_argv`, so test callers are mixed in with production ones. It also returned `callers_unresolved: 0`, a claim about the parser's own resolution, not about the program. The upstream chain (depth 2) adds two hops: `_nested_trees_recursive → _gitignored_paths` and `find_source_files → _git_ls_files`. Those two hops come from `doxygen_sqlite` (`exact`), not `ast`. The chain's depth-0 node reports `omitted: 4`, so it is capped.

The reply also carries relations that are not call sites:
- **threads**: `clew-first-build-`, with `member_count: 72`. This says the function is reachable from that thread's entry, not that the thread calls it.
- **requirements**: `REQ-DDB-CONFIG-001`, an annotation the code claims to satisfy.
- **covering_tests**: `test_mqtt_dispatch_accepts_an_inline_document_not_only_a_path`. The name has nothing to do with git, so this link looks like a weak attribution. Treat it as a pointer to check, not as coverage.
- **callees**: empty. For this function that is plausible, but an empty field is only a statement about what the index resolved.

**Why reading it as a list of call sites would be wrong.**

1. **It is a static, name-resolved graph.** An edge means the source names the callee at that place. It does not mean the call runs, and it misses calls made through function references, callbacks, dynamic dispatch, or other languages (a shell script or CMake invoking the Python).

2. **The direct callers are not all the git invocations.** `clew/guard/git.py` has bare literal argv such as `["git", "diff", …]` at lines 88, 104, 142, 152, 181 and 197. None of those appear as callers of `git_argv`, because they call `run_git`, and only `run_git` calls `git_argv`. `run_git` (line 72) rewrites the argv only when `cmd[0] == "git"`. So the literal sites are safe through `run_git`, but only because of that conditional. A caller list for `git_argv` would not show a site that bypassed `run_git` or built its argv some other way. The index does not show that gap. The test `test_every_git_invocation_disarms_the_inspected_trees_config` is what checks it, from the source text, not the graph.

3. **Depth decides what you see.** Depth 1 is only the direct layer. Who reaches `git_argv` through `run_git` or `find_source_files` is in the depth-2 chain, which is truncated and mixes provenance.

4. **Provenance and confidence differ by hop.** `resolved` (AST) and `exact` (doxygen_sqlite) are different evidence, and a single chain can mix them.

5. **Absence is not proof.** No caller listed means the index did not resolve one. It does not mean nothing calls the function.

**How to use it.** Read the direct callers as a starting set. Filter out tests if you want production paths. Then follow `run_git` upward, and grep for the exact argv pattern that the call-graph cannot see. For a safety property like this one, the source-level test is the authoritative check, and the graph is the map that tells you where to look.