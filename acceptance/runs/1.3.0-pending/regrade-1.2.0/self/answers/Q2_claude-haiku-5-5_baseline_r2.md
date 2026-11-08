**Short answer:** the reply separates the two cases by grading the empty result, not by a yes/no flag. Only one shape earns the strong "definitive, don't retry" wording, and every reply also names what it did and did not read. The strong wording is still a claim about this index's scope, not about the repository. I read the code only; I did not run a query against a built index.

**How the grading works** (`clew/mcp_server/emptiness.py`, `search_emptiness`)

| Empty `search` case | Wording | Confidence |
|---|---|---|
| One token, nothing in the symbol corpora read, and no unread corpus holds a match | `_DEFINITIVE`: "a definitive empty result… Do not retry" | Strongest. Still bounded by the scope (see below). |
| One token, but the index holds matching rows in a corpus `search` does not read | `_UNREAD_CORPUS`: "NOT DEFINITIVE… this index HOLDS matching rows…" with counts by kind | Negative. The name exists; it is just in a kind `search` skips. |
| One token, index has no file-docs corpus | `_NO_FILE_DOCS`: "NOT definitive. Rebuild with index(action='refresh')" | Not a negative. The index could not look. |
| Multi-token query | `_conjunction_note`: "NOT definitive", plus per-token hit counts and the token that emptied it | Weak. Usually "retry with fewer tokens." |
| Prose corpus (`corpus='prose'`) | Matches elsewhere → "NOT DEFINITIVE… these terms are in the symbol corpora." No prose corpus → "NOT definitive." | Only definitive when both prose and symbol corpora were read and neither holds the token. |

The single-token definitive case is the one that matters. `_verdict` gives it only when `q.unsearched_corpora` returns nothing, which subtracts the kinds `search` reads from the kinds the database actually holds. Its docstring records four earlier cases (classes, variables, macros, typedefs/enums) where the strong wording was false, which is why the check exists.

**The "did not look there" half** is carried by fields on every empty reply, not by the wording:

- `scope` (`_scope_payload`): covered file count, source tier (whole-repo vs declared), extensions, top levels. This is what separates "outside the indexed scope" from "not in the repo". `not_indexed` and `not_indexed_count` are present only when the build recorded them. Absent means "not recorded", not "nothing skipped".
- `not_searched` (`routing.py`, `RepoIndexes.not_searched`): for a sub-index answer, the other parts of the repo it did not read, built ones first, including known-but-unbuilt ones. A whole-repo answer lists nothing because it covered everything. A miss in a sub-index is therefore not definitive for the whole repo.
- `unsearched_corpus_hits`, `token_hits`: the checkable evidence behind the grade.
- The static `_SEARCHED` sentence lists the kinds read and says markdown and Kconfig prose are not searched.

**Confidence to give each answer**

- "Definitive, nothing unread matched" means the symbol corpora this index holds have no such name, within the scope it was built with. It does not mean the file is absent from the repo. A file outside the index scope is only visible through `scope`/`not_indexed`.
- "Not definitive" means look elsewhere: another corpus, a fewer-token query, a sub-index named in `not_searched`, or a rebuild.
- Missing `scope`/`not_indexed` on an older index means the reply cannot say what it covered. Treat the negative as weaker.

**Gaps I noticed**

- The unread-corpus check covers only the `memberdef` and `compounddef` kinds. Prose and Kconfig are handled by the static text and by `prose_emptiness`, not by the subtraction.
- The single-token definitive case does not check whether the file scope was complete. It only checks the index's own kinds, so "definitive" depends on the scope the build chose.
- The `rows` template says absent fields mean "does not apply". So a missing `not_indexed` means the build did not record it, not that nothing was skipped.