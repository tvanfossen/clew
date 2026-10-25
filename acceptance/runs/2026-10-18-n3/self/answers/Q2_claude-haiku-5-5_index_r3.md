The reply doesn't use one "empty" signal. It labels the empty result differently depending on which corpus was searched and what it covered, and each label carries a different amount of confidence.

**What I ran:** two searches against this repo with a made-up token. Both came back with zero rows, and the replies were worded differently.

| Probe | Reply's own label | What it licenses |
|---|---|---|
| `search` default corpus (symbols), two tokens | "NOT an error… and it is NOT a definitive negative either" | Weak. Only the symbol layer was read. Retry with fewer tokens or try `corpus='prose'`. |
| `search` corpus `prose`, one token | "This IS a definitive empty result from the database" | Strong, but only for markdown prose in the indexed set. |

**How the distinction is made:**

- **Scope is named in every reply.** The symbols reply lists 426 indexed files and their extensions, plus `not_indexed` extensions (`.rs`, `.toml`, `.sql`, `.csv`, extensionless files and others). It also reports `target`, the repository that was actually queried. The "did not look there" case is spelled out in `note`: markdown and Kconfig prose are not searched by the symbol corpus.
- **Conjunction misses name the culprit.** `token_hits` shows per-token counts, and the note says which token alone empties the match. Here both tokens were zero, so the retry advice was to drop them.
- **Corpora are graded separately.** The symbol corpus is never a definitive negative on its own. The prose corpus is, but only within its own scope.
- **Split repos add `sub_index` and `not_searched`.** Those fields name any vendored part that was skipped. The MCP guidance says to check them before concluding a symbol does not exist.

**Confidence each answer deserves:**

- **"Not in the indexed symbols"**: low. It's a candidate miss. Conjunction and token spelling can cause it, and it says nothing about markdown or unindexed file types.
- **"Not in the indexed prose"**: high, but only for indexed `.md` files. It says nothing about a `Makefile`, a CI config, a `.toml`, or a `.rs` file (the index covers only some languages), which the MCP guidance says the index cannot settle.
- **"Not in the repo"**: the index can't establish this on its own. Once the reply's `target` matches the intended repo and no `not_searched` part was skipped, a miss in the right corpus is good evidence. For anything outside the indexed set, a plain text search such as Grep is what settles it.

In short, a zero-row reply is a statement about the corpus and scope it names, not about the repository as a whole. Read `target`, `scope` and `not_searched` before reading the zero as absence.