**Short answer:** an empty reply is not a verdict by itself. The reply names where it looked and where it did not, and confidence depends on that list. I ran one probe against this repo to see the shape. The query was a nonsense term, so it shows the format, not a finding about the code.

**What the empty reply contains**

| Field | What it tells you |
|---|---|
| `count: 0`, `results: []` | Nothing matched in the corpus searched. |
| `note` | Says outright "NOT an error" and "NOT a definitive negative either." It also lists what was searched and what was not. |
| `token_hits` | Per-token counts. A multi-word query is a conjunction, so this shows which token emptied it. |
| `scope` | Files covered (426 here), top-level directories, and `not_indexed`: extensions the index holds but did not read (`.rs=2`, `.toml=2`, `.sql=1`, extensionless `=3`, and others). |
| `target` | The repository that answered. Check it matches the repo you meant. |

**"Not in this repo" versus "not where I looked"**

- **Searched and found nothing:** the symbols corpus was searched over indexed files. That covers function, variable, macro, type, and class names, their briefs, file docs, and the config symbols the repo gates on.
- **Not searched:** markdown and Kconfig prose, which need `search(corpus='prose')`. Files whose extension is in `not_indexed` were never read at all. Build files and CI configs are outside the indexed set entirely (per AGENTS.md).

So an empty symbols search means "no indexed symbol by that name." It does not mean "the concept is absent," and it says nothing about a `.rs` or `.toml` file that was never read.

**Confidence**

- **Symbols corpus, target is the right repo, no relevant extension in `not_indexed`:** reasonably strong evidence that no such symbol exists in the indexed C/C++/Python/JS/shell/CMake code. The tool itself declines to call this definitive.
- **Prose corpus, or a concept rather than a name:** weak. Retry with the prose corpus and a different word before concluding anything.
- **Symbol lives in an unindexed type** (here `.rs`, `.toml`, `.sql`, or extensionless files), or in a Makefile or CI config: no evidence either way. Read the file directly.
- **Multi-token query returns zero:** this proves only that the conjunction is empty. Retry with fewer tokens, as the note says, before reading the zero as absence.

The tool's guidance is to check `target` and any `not_searched` or `not_indexed` before concluding a symbol does not exist. That is the discipline the reply is built to support.