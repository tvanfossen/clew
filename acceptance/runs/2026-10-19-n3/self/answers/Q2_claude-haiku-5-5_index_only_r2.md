An empty reply doesn't say "absent" or "unsearched" in a single flag. It reports what was searched and leaves the verdict to you. I ran a search for a nonsense term to see the shape. It returned `count: 0`, `results: []`, and a `note` that says the result is "NOT an error and NOT a malformed call, and it is NOT a definitive negative either."

**What the reply shows, and what each field tells you**

| Field | What it tells you |
|---|---|
| `token_hits` | Per-token counts. A search is a conjunction, so these show which token emptied it. The note says to retry without the zero tokens. |
| `note` "Searched:" list | The corpora actually read: names and `@brief` of functions, variables, macros, typedefs, enums, enum values, macro expansions, classes/structs/unions, config symbols, and file docs. |
| `note` "NOT searched" | Markdown and Kconfig prose, which is `search(corpus='prose')`. Function bodies and inline comments are not in the searched list, so a word that appears only in code is not matched by `search`. |
| `scope` | File count (426 here), top-level directories, the extensions that were indexed, and `not_indexed` with per-extension counts (here `.rs=2`, `.toml=2`, `.sql=1`, `.lock=1`, and extensionless files). |
| `target` | The repository that answered. Check this first. |
| `not_searched` | Per the server instructions, names any sub-index that was not read. It was absent here, which fits a single whole-repo index, though the description only says what the key means and does not spell out its absence. |
| `staleness` | Present only if the index is older than the source. Absent here, so the index is current. |

**How much confidence each answer gets**

- **"Not a named symbol in the indexed set" (strong):** `target` is the repo you meant, there is no `staleness` block, every token is zero in `token_hits`, and the term is a name or a documented identifier. That supports "no indexed C/C++/Python symbol with that name," across the 426 files in the listed extensions.
- **"Not in the repo" (weak):** The same empty reply cannot support this. It does not cover prose, function bodies, inline comments, file types outside `scope`, or anything outside the indexed file set (the server says Makefiles and CI configs are out of reach). Before concluding a concept is absent, run `search(corpus='prose')`, and for `.rs`/`.toml`/`.sql` or build files, read the source directly.
- **Multi-token misses (weak):** A miss can come from one token alone. Retry with the single most distinctive token, since the conjunction makes a two-word query fail on either word.
- **Naming mismatch (unknown):** The index can't tell you whether the code spells the name differently for a different consumer, so a zero can also mean a different spelling exists.

In short, a zero from `search` is evidence about the indexed names, not about the repository. The reply gives you enough fields to judge which of those two you're entitled to claim, but it does not make that judgement for you.