The reply does not use one flag for both claims. Each empty `search` gets a verdict that is graded per call, plus a `scope` block that says what was indexed. The grading lives in `clew/mcp_server/emptiness.py` (`search_emptiness`, wired in at `tools_query.py:2390`). I read the code but did not run a query against a built index.

**How the two cases are told apart**

| Reply shape | Wording | What it licenses |
|---|---|---|
| One token, no hits in any corpus, and no rows in a corpus `search` doesn't read | "This IS a definitive empty result… Do not retry" | The index has no such name in the corpora `search` reads. |
| One token, but the database holds matching rows in an unread corpus (typedefs, enums, macros, etc.) | "NOT DEFINITIVE — this index HOLDS matching rows that search does not read: N kind" | The name exists. Use `dossier` rather than rephrasing. |
| One token, no file-level docs corpus in the index | "NOT DEFINITIVE… Rebuild" | The index cannot look at prose, so the miss proves nothing about prose. |
| Several tokens | "NOT definitive"; per-token hit counts name the dead token(s) | Matching is a conjunction. Retry without the token that matches nothing, or with fewer tokens. |

The unread-corpus check (`unsearched_corpora`, `query/symbols.py:1806`) works by subtraction: kinds present in the database minus kinds `search` reads. It only sees what is in the database.

**The scope block**

Every empty reply carries `scope`: file count, source tier (`declared`, `doxygen-guard` or `doxyfile`), top-level directories, extensions, and `not_indexed`. That last field lists file types that were in scope at build time but produced no rows. This is how "I did not look where it lives" becomes checkable: if the symbol's file extension is absent from `extensions`, or appears in `not_indexed`, the miss is a scope miss. The long derivation paragraph is removed from the reply and kept in `status`. If the index predates these stamps, the fields are omitted rather than shown as empty, so the reply doesn't claim "nothing was missed".

**How much confidence each answer deserves**

- **"Definitive" is confidence about the index, not the repository.** It means the name is absent from the searched corpora of this build's scope. It does not mean the repo lacks it.
- **Strongest case:** a single token, no unread-corpus hits, file docs present. This is solid for symbols and files in scope.
- **The gap:** `_verdict` never checks whether the query's likely file type is in scope. A definitive reply can still come back for a symbol living in an extension listed in `not_indexed`. The caller has to read the `scope` payload to rule that out, and the verdict text doesn't say so. I'd treat any zero-row answer as "absent from the index" until `scope` has been checked.
- **Multi-token and prose misses are never definitive.** The reply itself says so.
- **Build-time vs. query-time:** `not_indexed` is computed from the build's tree. The code comment in `corpus.py` notes the working copy may have changed since, so a file added after the build will not appear.

I did not verify whether depth-limited directories (recorded in `scope.py`) surface in the reply. I'd check that before relying on the scope block to rule them out.