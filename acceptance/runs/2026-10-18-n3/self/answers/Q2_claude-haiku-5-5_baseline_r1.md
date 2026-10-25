The reply separates the two cases in code, not in one sentence. The grading lives in `clew/mcp_server/emptiness.py`, and the scope it reports comes from `clew/query/models.py` and `clew/cli.py`. I read these files but did not run a live query against an index.

**How the reply tells the cases apart**

- **Scope block on every empty reply.** `search_emptiness` attaches a `scope` payload: file count, the scope source (`declared` or whole-repo), top-level directories and extensions. That lets the caller see what was covered at all, which is what "I did not look in the place it lives" depends on. The `reason` paragraph is dropped from this payload to save bytes; `status` still carries it.
- **Unread-corpus check.** `q.unsearched_corpora` asks the database whether the query's tokens match rows in a corpus `search` does not read. Any hit downgrades the verdict and is published as `unsearched_corpus_hits`, and the reply names the kinds and points to `dossier`. This is a database check, not a filesystem walk.
- **Conjunction and corpus checks.** Multi-token searches get per-token hit counts and are never called definitive. Prose searches on an index with no markdown corpus say "NOT definitive" and ask for a rebuild.
- **`not_indexed` stamp.** Recorded at build time by `_not_indexed_scope` in `cli.py`: file types the build walked that produced no rows, with counts. It is present only if the build recorded it, and the falsy-drop rule means an unrecorded report is absent rather than shown as empty.

**How much confidence each answer gets**

| Reply shape | What it licenses |
|---|---|
| "definitive", single token, file docs present, no unread hits | Strong, but only about this index. The token is absent from every corpus `search` reads. It does not prove the repo lacks it, because the index may be stale or the file may sit outside the declared scope. Check `scope` before trusting it. |
| "NOT definitive" (conjunction, prose-only miss, no file-docs corpus, unread hits) | No negative claim. Retry with the named token, use `dossier`, or rebuild. |
| `not_indexed` lists an extension | The file type was walked and yielded nothing. The counts are a snapshot from build time, so they can drift after edits. |
| `scope` is absent | Nothing is known about coverage. The index predates the field. |

The main gap: a "definitive" answer covers the index's scope, not the working tree. A file outside the derived scope with an extension the build never walked can only be identified through `scope`, `not_indexed` and `status`, and none of those is re-measured at query time.

The design intent is pinned in tests: `tests/test_emptiness.py::test_an_absent_symbol_keeps_the_definitive_note` guards the strong wording, and `tests/test_search_type_corpora.py::test_an_unread_corpus_downgrades_the_verdict` guards the downgrade. I did not run either test.