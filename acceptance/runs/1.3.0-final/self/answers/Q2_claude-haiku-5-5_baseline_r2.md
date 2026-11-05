The reply does not use one sentence for every empty result. `clew/mcp_server/emptiness.py` grades each empty `search` against what the index actually holds, and attaches a scope block that says what was read.

**How "not in the repo" is separated from "not looked at"**

1. **Unread corpora are checked first.** `search_emptiness` calls `q.unsearched_corpora` (`clew/query/symbols.py:1806`). That function takes the kinds present in the database and subtracts the kinds `search` reads (`SEARCHED_MEMBERDEF_KINDS`). If any of the remaining kinds (typedefs, macros, variables, and so on) hold a row matching the query, the reply says "NOT DEFINITIVE — this index HOLDS matching rows that search does not read", names the kinds and counts, and points to `dossier`. The check is derived by subtraction, so a new kind downgrades the verdict without an edit to the emptiness code.

2. **Multi-token queries are never definitive.** Search is a conjunction, so the reply reports per-token hit counts. If a token matches nothing alone, it is named and the caller is told to retry without it. Otherwise it tells the caller to use fewer tokens or `corpus='prose'`.

3. **A missing file-docs corpus blocks the strong wording.** For a single token with no unread hits, `_verdict` returns the strong "This IS a definitive empty result" text only if `has_file_docs` is true. Otherwise it returns "NOT definitive" and says to rebuild.

4. **Prose search has its own gates.** `prose_emptiness` says "no ingested markdown corpus" when the corpus is absent. If the token exists in the symbol corpora, it says "this repository DOES use these terms" and points to `search(corpus='symbols')`. Only when the prose corpus exists and the symbol corpora also miss does it return the definitive wording.

5. **Scope is always attached.** Every empty reply carries a `scope` payload with file count, top-level directories, extensions, and the source tier (whole-repo or declared). That tells the caller what the index covered. `_scope_payload` drops the long derivation paragraph to save bytes, and `status` still has it.

6. **File types that were in scope but not indexed are recorded at build time.** `cli._not_indexed_scope` (`clew/cli.py:2646`) compares the scanned files against the `path` rows and stores `ext=count` entries, capped at 12 extensions with an exact total. The query side reads that record (`clew/query/corpus.py:326`). An index built before the record existed shows no `not_indexed` key, which reads as "not recorded" rather than "nothing missed".

**How much confidence each answer gets**

| Reply | What it licenses |
|---|---|
| "definitive" (single token, no unread hits, file docs present) | Strong. The name is absent from every corpus `search` reads and from every other kind the database holds. Retrying the same query will not help. |
| "NOT definitive", unread hits named | The name exists in this repo's index under another kind. Do not conclude absence. Use `dossier` on the name. |
| conjunction note | No conclusion about the repo. Drop the named token or use fewer tokens. |
| prose "NOT definitive" (no corpus, or present in symbols) | Either the corpus was never built, or the term is written elsewhere. The first says rebuild; the second says look in symbols. |

**Gaps I found**

- The "definitive" wording does not consult `not_indexed`. If a symbol lives in a file type the build skipped, the note can still say "definitive", and the only contrary evidence is the `not_indexed` entry in the `scope` payload. The sentence is stronger than the check behind it for that case.
- The verdict describes the database as built, not the working tree. Staleness is handled elsewhere (`status`, freshness), and I did not trace how a stale index shows up in an empty reply.
- `_SEARCHED` names what was read and what was not, but the scope sentence says "whole-repo" or "declared" without saying how a scope miss would look from the caller's side.

I read the code only and did not run the test suite, so these conclusions rest on reading the functions above.