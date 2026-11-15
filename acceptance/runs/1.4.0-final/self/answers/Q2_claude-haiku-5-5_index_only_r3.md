The reply separates the two cases through its `note` and `scope` fields, not through a single flag. I ran a probe with a made-up name to see it. The reply came back with `count: 0` and a note calling it "a definitive empty result from the database, NOT an error." That note also lists exactly what was searched and what was not.

**What counts as "looked":**

- **Searched:** names, `@brief` text, macros, typedefs, enums, enum values, classes/structs/unions, config symbols, and file docs. A miss here is a real miss in those layers.
- **Not searched:** markdown and Kconfig prose (use `corpus='prose'`), and function bodies, where keys and literals live (use `corpus='code'`). The note names these, so a conceptual phrase or a string literal can miss here and still exist.
- **Not indexed at all:** `scope.not_indexed` lists extensions and file types the index skips (for example `.rs`, `.toml`, `.sql`, `.csv`, extensionless files). This list is the blind spot most likely to be missed. The per-query note does not mention it. A Rust or TOML hit that comes back empty looks identical to a true absence, so you have to read `scope` to know.
- **Scope of the read:** `scope.source` and `file_count` say what was covered (here, whole-repo, 426 files). `target` names the repository that answered. If the repo is split into parts, a `not_searched` field lists the parts that were not read. That field appears on `dossier` replies, and I did not see it on this search reply.

**Confidence each answer deserves:**

| Reply | What it licenses |
|---|---|
| Empty, and the name's kind is inside a searched layer, with `scope` covering the file's extension | Strong: "not defined here as a symbol." |
| Empty, but the answer could live in prose or a function body | Weak: retry with `corpus='prose'` or `corpus='code'` before concluding anything. |
| Empty, and the file's extension is in `not_indexed`, or the repo is split and the part is in `not_searched` | None: "I did not look." Read the source directly. |

The reply also says not to retry the same query, so a second identical search is wasted effort. A real "not here" needs the other corpora or the `scope` check, not a repeat.