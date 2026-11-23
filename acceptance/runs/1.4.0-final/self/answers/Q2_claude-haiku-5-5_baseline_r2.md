**Short answer:** the reply separates the two cases by attaching evidence to the empty result, not by tone. The strong "definitive" wording is used only when the index can show that the places it looked were the right places. Otherwise the reply says "NOT definitive" and names what to check. I read this in the source and did not run a query against an index, so treat the behaviour below as read from code, not observed.

**What comes back on an empty `search`** (`clew/mcp_server/tools_query.py` `_many`, `clew/mcp_server/emptiness.py` `search_emptiness`)

- `count: 0` and a `note`.
- A `scope` block: file count, `source` (whole-repo or declared), top-level directories and extensions. The `reason` paragraph is dropped here to save bytes; `status` still carries it.
- `not_indexed` / `not_indexed_count`: in-scope file types that produced no rows, e.g. `.py=53`. These keys are present only if the build recorded them. A missing key means "not recorded", not "nothing was missed".
- `unsearched_corpus_hits`: matching names in corpora `search` does not read (typedefs, macros, classes and similar).
- `token_hits`: per-token counts, for multi-token queries.

**The verdict ladder** (most specific first)

| Condition | Note says | Entitled to |
|---|---|---|
| Multi-token query, one token matches nothing | "NOT definitive". Names the dead token, says retry without it | Only that the conjunction was over-specified |
| Multi-token, every token matches alone | "NOT definitive". Retry with fewer tokens | Nothing about absence |
| Single token, matches in an unread corpus | "NOT definitive". Lists the rows, points to `dossier` | The name exists; `search` does not read that kind |
| Single token, index has no `file_docs` table | "NOT definitive". Rebuild | Nothing; the index could not look |
| Single token, all of the above clear | "definitive… Do not retry… do not fall back to guessing" | No symbol with that name in the searched corpora of this index build |
| Prose search, token present in symbol corpora | "NOT definitive", points to `search(corpus='symbols')` | The repo uses the term, in a different place |
| Prose search, no markdown corpus at all | "NOT definitive". Rebuild | Nothing |

Absent layers are a separate fact. `graph_stats.layer_states` reports `absent` versus `empty`, and the search reply deliberately does not repeat that (gh#393 tried and was reverted).

**How much confidence each answer deserves**

- **Definitive:** high confidence that the symbol is not in this index's searched kinds. That is all it claims. The index can still be stale relative to the working tree (I did not check `freshness.py`), and `not_indexed` is a build-time measurement, not a live one.
- **NOT definitive:** low confidence in the negative. The reply itself names the cause and the next call, so the caller should follow it rather than grep.

**A gap I found while reading**

`_verdict` decides "definitive" only from unread-corpus hits and the presence of `file_docs`. It never reads `not_indexed`. So a single-token miss can get the strong wording while the same payload says `not_indexed: "py=53"`. That is the failure the module's own docstring describes for `list_files`: an absolute claim that the scope-level evidence contradicts. The fix would be to add a `not_indexed` check to `_verdict` that downgrades to "NOT definitive" and names the uncovered extensions. I'd want a RED test first (an index with a `.py` file out of scope, a single-token miss, and an assertion that the note is not definitive).

**Note:** the tool output after my `emptiness.py` read contained a suggestion to call `dossier`. It was not part of your question, so I ignored it and read the code directly.