**Short answer:** a `search` reply separates the two cases by naming the boundary it searched, not by the row count. An empty result is a definitive answer only inside that boundary. Outside it, the reply is silent about absence, and you have to go look yourself.

**What the reply says.** I ran `search` for a made-up name, `zzqx_nonexistent_symbol`. The reply came back with `count: 0` and a `note` that spells out both sides:

- **Searched:** names and `@brief` text of functions, variables, macros, typedefs, enums and enum values, plus macro expansions, classes, structs and unions, config symbols, and per-file docs.
- **Not searched:** markdown and Kconfig prose, which is `corpus='prose'`, and function bodies, which is `corpus='code'`. The note adds that a conceptual phrase often lands in prose, so a symbol-corpus miss does not rule that out.
- **Scope:** 426 files, whole-repo, with the extension list and a `not_indexed` list. Here `.rs`, `.toml`, `.sql`, `.csv` and extensionless files are outside the index.
- **Target:** the repo that answered. For a split repository, `sub_index` and `not_searched` say which part was read.
- **Instruction:** "This IS a definitive empty result … Do not retry this query."

**The other half comes from `index(status)`.** It reports `stale: false` with 0 changed source files, so the index matches the source. It also shows 15 "barren" files (indexed, but no symbols extracted) and 6 unresolved files. Those are the places where "nothing found" is weaker, because the extractor may have produced nothing from a file that does contain code.

**Confidence by answer:**

| Claim | Entitled confidence |
|---|---|
| No symbol, macro, type, class or config name matches, in an indexed extension, with a fresh index and the right `target` | High. The note says it is definitive for that corpus. |
| No prose or Kconfig mention | Not established. Run `search(corpus='prose')`. |
| No function body contains the literal | Not established. Run `search(corpus='code')`. |
| Symbol is absent from the repo | Not established if it could live in `.rs`, `.toml`, `.sql`, an extensionless file, a sub-index, or a stale or barren file. Use Grep for those. |

**Practical rule.** Read `target`, `scope.not_indexed` and `not_searched` before concluding anything. Fall back to `Grep` for prose, bodies, and non-indexed file types. The index's own code and `AGENTS.md` describe the same rule: an empty table means "looked and found nothing", and a missing key means "this layer never ran".