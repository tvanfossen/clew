The reply doesn't use one "no results" signal. It gives several fields that separate the cases, and each carries a different amount of confidence.

**What I ran:** `search` for `zzqxv nonexistentwidget` (symbols) and `zzqxv` (prose). Both returned `count: 0`, but the notes differ.

**Symbol search, multi-token miss:**
- `note` says it is "NOT an error and NOT a definitive negative."
- `token_hits` gives per-token counts (`zzqxv=0`, `nonexistentwidget=0`). Matching is a conjunction, so the note names the tokens that emptied the result. The fix is to retry with one distinctive token, not to conclude absence.
- `note` also lists what was searched: names, `@brief`s, macros and expansions, types, config symbols, and file docs. It says markdown and Kconfig prose were not searched, and points to `corpus='prose'`.
- `scope` gives the reach: 426 files, whole repo, the indexed extensions, and the `not_indexed` extensions with counts (e.g. `.rs=2`, `.toml=2`, `.sql=1`, no-extension files=3).
- `target` names the repository that answered.

**Prose search, single-token miss:** the note says "This IS a definitive empty result from the database." That is stronger, but only for the indexed markdown.

**The "did I look in the right place" channel:**
- `target`: confirms which repo was queried. Wrong target means the answer is about the wrong repo.
- `scope` / `not_indexed`: lists extensions and files the index never read.
- `not_searched`: appears when a sub-index (e.g. vendored code) was skipped. It was absent here, so nothing was skipped.
- `staleness`: appears only when the index is older than the source. It was absent here, so the index is current.

**Confidence I would assign:**

| Situation | What an empty reply supports |
|---|---|
| Single token, empty prose corpus, file type in `scope`, no `not_searched`/`staleness` | Strong: the repo indexed text of that kind and does not contain it |
| Multi-token symbol miss | Weak until retried with each distinctive token alone |
| Symbol search, no prose check | Moderate: prose and Kconfig were not read |
| Target file is in a `not_indexed` extension, a Makefile, a CI config, or outside the indexed set | None: the index cannot answer. Read the file directly |
| `not_searched` or `staleness` present | None until the named part is searched or the index is refreshed |
| Name spelled differently per consumer (e.g. macro-generated or language-bound names) | Weak: the index can't settle cross-spelling |

**Short version:** an empty reply means "not found in these corpora, over this file set, in this target." Only the single-token prose miss on indexed text approaches "the repo does not contain it." Everything else needs a retry with a single token, a prose search, or a direct file read before you conclude the thing is absent.