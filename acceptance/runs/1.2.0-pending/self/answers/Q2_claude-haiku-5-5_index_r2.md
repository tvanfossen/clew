The reply separates the two cases by naming the place it looked, not by a flag that says "absent" or "not checked." Two live calls showed the shape.

**What an empty reply says about where it looked**

- **`scope`** lists what was covered: 426 files, whole-repo, with extensions and top-level directories. It also lists `not_indexed`, the extensions the index skipped here: `.rs=2`, `.toml=2`, `.lock=1`, `.sql=1`, `.csv=3`, no-extension=3, and others, 14 kinds in all.
- **`note`** says what was searched and what was not. For my zero-row query it said the symbol names, `@brief` text, macros, types, config symbols and file docs were searched, and that "markdown or Kconfig prose" was **not** searched, pointing to `corpus='prose'`.
- **`target`** names the repository that answered. Check it before concluding anything.
- **`not_searched`** appears on multi-index repos, naming parts of the repo that were not read. I did not hit that case here.
- **`staleness`** appears only when the index is older than the source. Its absence means the index is current.

The design follows the codebase rule "absence is not emptiness" (AGENTS.md). Zero rows is a measured answer, not an error. The reply says so explicitly and tells you not to retry. A missing `staleness` or `not_searched` key means nothing was missed, not that the field was forgotten.

**How much confidence each answer gets**

- **"The repository does not define that name."** Strong, but only within the scope. A zero-row symbol search over 426 indexed files, with names and briefs covered, is good evidence that no indexed function, type, macro or file doc is named that. Trust it.
- **"The repository does not contain that text."** Weak. The search matches names and `@brief` text, not function bodies, comments or prose. A concept described in a Markdown file, a Makefile, a CI config, a Kconfig help string, or a `.rs`/`.toml`/`.sql` file falls outside what this search reads. Here the `.rs` and `.toml` files exist but are not indexed, so a Rust or TOML symbol would return zero rows even though it exists.
- **Conceptual phrases.** Use `corpus='prose'` before concluding that a concept is absent. The reply itself suggests it.
- **Multi-token queries.** Tokens must all match in one unit. The tool description says a multi-token miss names the token that emptied it. I did not test that case, so I am relying on the documentation there.

**Practical rule:** treat "no rows" as "not among the indexed symbols, in the indexed files." Before reporting absence, check `scope.not_indexed`, try the prose corpus, and fall back to grep for anything outside the indexed extensions.