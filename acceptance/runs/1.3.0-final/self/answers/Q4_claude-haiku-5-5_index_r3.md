**What's in the answer.** For `main` (resolved to `acceptance/__main__.py:644`), `dossier` returned a `callers` list where each row has a name, file, `confidence` (every row here was `exact`), `edge_class` (`call`), and `source` (`doxygen_sqlite`). Test methods also carry a `qualified` name. Beside the list sit `callers_unresolved` (0 here), `context_undecidable`, `_limited` (25 callers exist, 10 shown), and the `covering_tests` and `requirements` fields, which tell you what exercises the function, not who calls it. `search` describes the callers relation as "its callers plus the writers it reads from," so it can also include dataflow writers, not just call sites. The `edge_class` field and the test `test_callers_includes_fnptr_dispatch` show that function-pointer dispatch is also counted as a caller.

**What would make it wrong to read it as a list of call sites:**

1. **Name collisions.** The reply reported 8 candidate identities of 25 total named `main`. The contract says neighbour rows are shared across every identity that matches the name, and the `callers` here include a C test file (`tests/data/csample/test/test_sound.c`) and `scripts/hook_probe.py`'s `_report`. I did not verify whether those actually reach `acceptance/__main__.py:main`. Oddly, no `ambiguous` block appeared, even though the tool says that block marks multi-signature matches. Re-asking with `qualified=` is the fix.

2. **Truncation.** `max_neighbors` defaults to 10 and the reply discloses that 25 exist. A short list is not a complete list unless `_limited` is absent.

3. **Unresolved is not zero.** A call that failed to resolve to an indexed function does not appear as a caller. It is counted in `callers_unresolved`. The repo's own test `test_an_empty_callers_list_reports_what_was_refused` exists because an empty `callers: []` can mean "nothing calls it" or "every caller failed to resolve." Only the count distinguishes them.

4. **Static, not runtime.** The list is what the index resolved at build time. Calls through a Makefile, CI config, shell script, or anything outside the indexed file set will not appear. The MCP instructions say this explicitly.

5. **Mixed edge types.** Rows can be direct calls, function-pointer dispatch, or writers feeding the function through shared data. Treating all of them as "who calls this" overstates direct invocation. The `edge_class` and `confidence` fields are there to separate them.

6. **Tests are callers too.** Most rows for `main` are test functions. For impact analysis, filter by file or `qualified` to separate production callers from test callers.

**Bottom line:** the answer is a set of resolved, build-time edges with confidence and edge-class labels, plus disclosed gaps (unresolved count, truncation, name-shared identities). Read it as "these resolved edges exist," not "these are all the callers." Use `qualified=` on ambiguous names and check `callers_unresolved` before concluding that nothing calls a function.