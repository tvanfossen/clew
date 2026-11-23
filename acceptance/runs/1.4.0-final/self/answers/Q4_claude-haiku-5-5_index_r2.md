The answer is a set of static caller edges, not a proof that every relevant call goes through the function. I checked this on `git_argv` (`clew/gitenv.py:89`), which the index reports with:

- **Callers, grouped by file, one hop up:** `_detect_git_version` (guard/main.py), `_git_ls_files` (guard/tags.py), `_gitignored_paths` and `_is_dependency_of_parent` (scope.py), `run_git` (guard/git.py), `tracked_files` (propose/notindexed.py), and a test, `test_the_disarmed_key_list_reaches_the_argv`.
- **Callees:** empty. This function calls nothing indexed, so the empty list is a real answer about its body, not a gap.
- **Requirement and tests:** it carries `REQ-DDB-CONFIG-001` and a `covering_tests` entry.
- **Threads:** it is reachable from the `clew-first-build` thread through `_first_build_worker`, with `confidence: medium` and `source: ast_spawn`.
- **Liveness, body, and `@version`:** the verbatim body and docstring come back with it.

**What the answer means:**

- **It is a graph of resolved edges.** Each caller is a name the parser resolved to this symbol. The `ambiguous` and `candidates` fields are how the index says a name matched several things. Here `candidates` is empty, so the resolution was unambiguous. If that field were non-empty, the caller rows would be shared with other symbols and should not be attributed to this one.
- **It is one hop by default.** The list is direct callers only. The transitive picture needs `depth` with `direction: back`, which walks further up the graph.
- **Absence is not proof.** A git call made through `subprocess` with a literal `"git"` argv, through `getattr`, a string-built command, or dynamic dispatch would not appear as a caller. The security claim rests on `tests/test_security_surface.py` asserting that no site builds its own argv, and that test is a second, independent check. The caller list alone cannot establish it.
- **Coverage edges are weaker than call edges.** `covering_tests` lists `test_mqtt_dispatch_accepts_an_inline_document_not_only_a_path`, a test whose name has nothing to do with git argv. Treat that as a suspicious association to verify, not as evidence the defence is tested.
- **Thread reachability is a claim about spawning, not about runtime.** The `clew-first-build` link says the function is reachable from that thread's code path. It does not say the call executes on every build, and its confidence is medium.
- **The name is the key.** Callers are matched by symbol identity, so a function with the same short name in another module would need `qualified` to tell apart. This is why the index asks you to pass `qualified` back when a name is ambiguous.

**Reading it correctly:** the list tells you where the index can see a resolved call. It is an answer to "who statically calls this," and it is strong for that. It is weak for "is every path through this rule covered," and for that you need the test that asserts the absence, or a search of the code corpus for raw `git` invocations (`search(corpus='code')`), which would catch what the call graph cannot.