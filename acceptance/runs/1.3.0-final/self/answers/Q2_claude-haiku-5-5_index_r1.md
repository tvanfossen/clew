**Short answer:** the reply separates the two cases by what it says it searched, not by a bare "not found." A no-row reply is strong evidence about the indexed scope and weak evidence about anything outside it. Confidence should follow the scope, not the empty result.

I ran two searches with a made-up token to see the real shape:

- `search` (default symbols corpus) returned `count: 0` with a `note` saying the result is "a definitive empty result from the database, NOT an error and NOT a malformed call," and listing what it searched: names, `@brief`s, macros, typedefs, enums, classes, config symbols and file docs. It also says what it did not search: markdown and Kconfig prose (point to `corpus='prose'`) and function bodies (point to `corpus='code'`).
- `search(corpus='code')` also returned zero, with the same definitive note.

**What tells "not in the repo" apart from "not looked there":**

| Field | What it tells you |
|---|---|
| `scope` | Which files were indexed: `file_count` (426 here), `top_levels`, `extensions`, and `not_indexed` with counts for everything skipped (`.rs=2`, `.toml=2`, `.sql=1`, extensionless files=3, and so on). This is the main "did we look there?" signal. |
| `note` | Names the corpora searched and the ones that were not. |
| `target` | Which repository answered. A wrong target makes the miss meaningless. |
| `not_searched` | Named on dossier and search replies when part of a split index was not read. It was absent here, so no sub-index was skipped. |
| `staleness` | Present only when the index is older than the source. Absent here, so the index is current. |

**Confidence each answer deserves:**

- **"Not indexed symbol with this name"** — high, but only inside the stated scope. The reply is authoritative for the 426 indexed files and the listed corpora. A symbol named only in a file type on the `not_indexed` list, such as Rust, TOML, SQL, extensionless scripts, a Makefile or CI config, will never appear, so a miss tells you nothing there.
- **"No function body contains this literal"** — high for indexed function bodies. A string in a `.md` file, a Kconfig help text or a comment outside a function is not covered by this corpus.
- **"Repository does not contain it"** — low to medium. The index cannot say that. It can only say "not among the indexed declarations." Confirm by grep in the place the `scope` block says is not indexed.
- **"Index is wrong or stale"** — checked by `staleness`, which was absent here.

**What I did not verify:** I tested only a single-token miss. The tool description says a multi-token miss names the token that emptied the result, and I did not observe that.

**Practical rule:** on zero rows, read `scope.not_indexed` and the `note`'s NOT-searched list. If the thing you want could live in either, fall back to `search(corpus='prose')`, `search(corpus='code')`, or Grep over the uncovered extensions before concluding it is absent.