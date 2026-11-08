The reply separates the two cases through its wording and through a `scope` block attached to every empty result. The confidence it grants depends on which branch fired. I checked this in `clew/mcp_server/emptiness.py`, and a zero-row `search` for a nonsense token on this repo returned the strong wording with the scope attached.

**What every empty reply carries.** Each zero-row `search` includes a `scope` payload: the file count (426 here), the source tier (`whole-repo`), the top-level directories, the indexed extensions, and `not_indexed` counts for extensions the index skipped (`.rs`, `.toml`, `.csv`, and others). It also includes a `Searched:` clause that names the corpora read (names and `@brief` of functions, variables, macros, typedefs, enums, classes, config symbols and file docs) and says prose and Kconfig text were not searched. The point is that the caller can tell "outside the scope" from "not in the repo" without making another call.

**How the reply grades the empty result:**

| Situation | Wording | Confidence it earns |
|---|---|---|
| One token, no hits in any unread corpus, file docs present | "definitive… Do not retry this query or fall back to guessing" | Certain about the searched symbol corpora. Not certain about prose, and not certain about files outside the scope or in unindexed extensions |
| One token, but the index holds matching rows in a corpus `search` does not read | "NOT DEFINITIVE… holds matching rows… Ask for it by name with dossier" | The name exists; `search` just cannot return that kind |
| One token, but the index has no file-docs corpus | "NOT definitive… Rebuild with index(action='refresh')" | Nothing; the index could not have matched a conceptual query |
| Several tokens | "NOT definitive… Token(s) X match nothing alone… RETRY WITHOUT THEM", or "every token matches alone… RETRY WITH FEWER TOKENS" | A diagnosis of what emptied the conjunction, not a claim about the repo |
| `search(corpus='prose')`, token found in symbols | "NOT DEFINITIVE… this repository DOES use these terms" | The term exists; it is just not in prose |
| `search(corpus='prose')`, no prose corpus | "NOT definitive… Rebuild" | Nothing |
| `search(corpus='prose')`, token absent everywhere | "definitive" | Strong: the prose and symbol corpora were both read |

The module's own rule is that the strength of a sentence has to be earned per call. The unread-corpus check and the file-docs check run only after the result is already zero, so they add no cost to normal queries. The `gh#393` note in the same file records a deliberate refusal to downgrade on every absent gate layer. That would have hedged almost every reply.

**The gap.** The single-token "definitive" verdict does not check the query against the scope. `_verdict` looks only at unread corpora and file docs. If the symbol lives in a `.rs` file (this index skips 2 of them) or outside the 426 indexed files, the reply still says "definitive" and relies on the caller reading the `scope` key. The module's docstring says scope misses were a real false claim and were handled for `list_files`, which has since been removed. So for `search` the scope is disclosed but not used to downgrade the verdict. I did not test that case directly; the conclusion comes from reading the code.

**How much confidence each answer deserves:**
- "Definitive" with `scope` showing the target's extension is indexed: good evidence that the symbol is absent from the searched symbol corpora of the indexed files. Use it to stop searching the index for that name.
- "Definitive" with the target outside the indexed extensions or the file set: no evidence. Fall back to `grep` or `Read`.
- Any "NOT definitive" reply: the text itself says to retry or go elsewhere. Follow it.