**Short answer:** the reply separates the cases by what it can check, not by how it words the miss. A single-token miss gets the strong "definitive" wording only after the server confirms the index holds no matching rows elsewhere. Almost all of the confidence comes from the index's coverage, not the repository's contents. One gap: the not-indexed file-type report is attached to the reply but does not change the verdict wording.

I read the code (`clew/mcp_server/emptiness.py`, `clew/query/symbols.py`, `clew/query/corpus.py`, `clew/cli.py`, `tests/test_not_indexed_report.py`). I did not run a query or the tests.

**What the reply checks before it speaks**

| Check | Source | What it changes |
|---|---|---|
| Does any unread corpus hold this name? | `q.unsearched_corpora` (`symbols.py:1806`) | Any hit makes the reply "NOT DEFINITIVE" and names the rows, e.g. "2 typedef". This outranks everything else. |
| Is it a multi-token conjunction? | `_conjunction_note` | Never definitive. It names the tokens with zero hits and says to retry without them. |
| Does the index have a file-docs corpus? | `has_file_docs` | If not: "NOT definitive, rebuild". |
| Does the index have a markdown corpus? (prose search) | `has_prose_corpus` | If not: "NOT definitive, rebuild". |
| Did the build record files it could not index? | `scope.not_indexed*`, stamped at build time | Shown in the `scope` payload only. The build has to stamp it; older indexes omit the key rather than report "nothing missed". |
| What area does the index cover? | `scope` payload (`source`, file count, top dirs, extensions) | Lets the caller tell "outside the scope" from "not in the repo". |

**Confidence each answer gets**

| Reply | Claim it makes | Entitled confidence |
|---|---|---|
| Single token, no unread hits, docs corpus present | "Definitive… do not retry" | High that the indexed symbol corpora lack the name. Scope-limited, not repo-wide. |
| Single token, unread corpus holds it | "NOT definitive; the name exists" | The name exists in the repo. Use `dossier`. |
| Multi-token, zero-hit token named | "Not definitive; retry without X" | Low on the whole query. High on the named token alone. |
| Multi-token, every token matches alone | "Retry with fewer tokens" | None on the query. The tokens exist, but no single unit holds all of them. |
| Prose miss, token present in symbols | "NOT definitive; it is in symbol corpora" | Moderate. The term exists in code, not in the prose the search read. |
| Prose miss, token absent everywhere | "Definitive" | Same as the symbol case. |
| No docs or prose corpus | "NOT definitive; rebuild" | None. The index cannot look. |
| `not_indexed` present | Scope payload only | Build-time snapshot of file types with no rows. Stale if files changed after the build. |

**The gap**

`_verdict` (`emptiness.py:361`) takes only the database and the unread-corpus hits. It does not look at `not_indexed_count`. So a single-token miss in an index that skipped `.sh` files still returns the strong "definitive… do not retry" note. The `not_indexed` entries appear only in the `scope` payload, where a caller may not read them. The module's own docstring says the case "read the file directly" exists precisely for this. I found no test that covers this combination; the not-indexed tests cover the stamping and the payload only.

The fix is small: have `_verdict` downgrade when `scope.not_indexed_count > 0`, and name the file types in the note. Before making that change I'd want a RED test that builds an index with a `.sh` file missing and asserts the note is not definitive.