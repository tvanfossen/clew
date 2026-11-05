The reply separates the two cases mainly through its `note`, `scope` and `token_hits` fields, not through a single flag. I ran two searches against this repo to see the actual shapes.

**What distinguishes "not here" from "not looked"**

- **Scope is reported.** The symbols reply carries a `scope` block: 426 indexed files, the top-level directories, the indexed extensions (`.c .cpp .h .json .md .py .yaml`), and a `not_indexed` list with counts (`.rs=2`, `.toml=2`, `.sql=1`, no-extension=3, and so on). That list is the direct answer to "did I look where it lives?"
- **Corpus coverage is named.** The symbols note lists what was searched (names, `@brief`, macros, types, enum values, file docs) and what was not (markdown and Kconfig prose, function bodies). It points to the corpus for each gap.
- **Conjunction is diagnosed.** `token_hits` shows per-token counts, and the note says which token emptied the match. Here both tokens were zero, so the note tells the caller to retry with fewer tokens, not to conclude absence.
- **Answers come from a named target.** Every reply has `target`, so you can see which repository was queried.

**Confidence each answer deserves**

| Reply | What it licenses |
|---|---|
| Symbols, zero rows | Nothing yet. The note calls it "NOT a definitive negative" and says to retry in `prose` or `code`. |
| Code corpus, zero rows | Strong evidence that no function body in the indexed files contains the literal. The reply calls this "definitive" and says not to retry. |
| Either, indexed extensions | Good evidence the thing is absent from those files, within the corpus searched. |
| Either, a `not_indexed` extension or outside the index | No evidence either way. The thing may simply be in a `.rs`, `.toml` or `.sql` file, a Makefile, a CI config, or another target. |

**Where the reply overstates**

The code-corpus reply's "definitive" label is stronger than its own evidence. It carries no `scope` block, so a caller reading that reply alone cannot tell that `.rs`, `.toml` and `.sql` files were never read. The claim holds only for indexed function bodies. The symbols reply is more honest because it does include `scope`.

Two things I did not check: whether `staleness` appears on a stale index (the tool docs say it does, and I saw none here), and whether `not_searched` appears on search replies or only on dossier. The tool documentation says it appears on dossier, and I did not see it in either search reply.

**Practical rule:** treat a zero as "not in the indexed function bodies or symbols of these extensions." Before concluding a thing does not exist, check `scope.not_indexed` and search the other corpora. For anything in a non-indexed file type, read the source directly.