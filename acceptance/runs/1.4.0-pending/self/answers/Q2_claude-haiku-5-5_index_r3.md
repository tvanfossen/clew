A zero-row reply does not carry one verdict. Its wording and its `scope` block together say what was searched, and how far the answer can be trusted depends on which case you are in.

**What I checked:** I ran `search` for a made-up token. It returned `count: 0` with a note calling the result "definitive," plus a `scope` block: 426 files, whole-repo, top levels, extensions, and `not_indexed` (`.rs=2`, `.toml=2`, `.csv=3`, and others). The grading logic is in `clew/mcp_server/emptiness.py`.

**How the reply separates the two cases**

- **Scope is always reported.** Every empty reply carries `scope` (file count, source tier, extensions, top levels, and `not_indexed` when recorded). That is the field that distinguishes "outside what was indexed" from "not in the repo."
- **Unsearched corpora are checked.** `search` reads symbol names, `@brief` text, macros, classes, config symbols, and file docs. It does not read markdown or Kconfig prose, or function bodies. If the index holds a matching row in a corpus `search` skips, the reply says "NOT DEFINITIVE" and names the rows and the tool to use (`dossier`, `search(corpus='prose')`, or `search(corpus='code')`).
- **Multi-token queries are never definitive.** A zero-row multi-token search is a conjunction. The reply reports per-token hit counts. A token with zero hits is the cause, so the advice is to retry without it. If every token matches alone, the advice is to use fewer tokens.
- **The absent-corpus case is named.** If the index has no file-docs corpus or no prose corpus, the reply says it "had nowhere to match" and is not definitive. The code says an index that cannot look must not report a negative.

**Confidence by case**

| Empty reply | Entitlement |
|---|---|
| Single token, no unread-corpus hits, file docs present | Strong. Absent from the symbol corpora of the indexed scope. Retrying will not help. |
| Multi-token conjunction | None. Retry with the token(s) the reply names. |
| Prose search, token present in symbols | None. The repo uses the term; it is written somewhere the prose corpus does not read. |
| Corpus absent (file docs or prose) | None. Rebuild, or use another corpus. |

**Gap I found:** The "definitive" verdict does not check `scope.not_indexed`. `_verdict` only looks at unread corpora and whether file docs exist. The extension-based downgrade ("this file type is outside the index") existed only for the deleted `list_files` tool. In this repo, a symbol defined in one of the two `.rs` files would likely still get the strong wording, even though `.rs` is in `not_indexed`. I inferred that from the code and did not test a Rust symbol. Until that is fixed, check `scope.extensions` and `scope.not_indexed` yourself before accepting a definitive miss. The reply does not do that comparison for you.