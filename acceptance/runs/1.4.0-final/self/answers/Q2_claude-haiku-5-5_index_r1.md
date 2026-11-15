**Short answer:** the reply separates the two cases by what it says about its own reach. A bare "no rows" is not the signal. The `note` field carries the grading, and it is only allowed to claim certainty about the places the search actually covered.

**What I observed.** I searched for a made-up token, `zzqx_nonexistent_symbol_probe`, against this repository. The reply came back with `count: 0` and a `note` that:

- Calls the result a definitive empty result from the database, "NOT an error and NOT a malformed call", and tells the caller not to retry.
- Lists what was searched: names, `@brief` text, macros, typedefs, enums, classes, config symbols, and file docs.
- Lists what was not searched: markdown and Kconfig prose (point to `corpus='prose'`) and function bodies (point to `corpus='code'`).
- Gives a `scope` block: `source: whole-repo`, 426 files, the top-level directories, the extensions that were read, and `not_indexed`, which names the file types the index never read (for example `.rs=2`, `.toml=2`, `.sql=1`, and files with no extension).
- Gives the `target` path, so you can confirm the index is looking at the repository you meant.

**How the code grades it** (`clew/mcp_server/emptiness.py`). The module's own comments describe three outcomes:

| Outcome | When | Confidence it earns |
|---|---|---|
| Definitive | A single token, matched nowhere in the searched layers, and nothing in an unread corpus could hold it | High, but only about the index. It is a statement about the scoped files and layers. |
| Not definitive | A multi-token conjunction, a corpus the index does not read, or an index with no layer that could hold the match | Low. The reply names the next step: another corpus, or `index(action='refresh')`. |
| Error | Malformed call | None. Not a result. |

The wording is graded, not fixed. The module has a test that a note claiming certainty must have earned it. It also says that the definitive note is kept only when nothing unread could have matched.

**How much each answer is entitled to:**

- **"Not in this repository"** is only supported when the reply is definitive *and* the place the name would live is inside `scope`. "Not in the symbol layer" does not mean "not in the repository". A function body, a Markdown file, a `.rs` file, or a Kconfig file can hold the name without a symbol row.
- **"I did not look there"** is what `not_searched` and `not_indexed` report. Those are the signals to act on: switch corpus, read the source directly, or check whether the file type is covered at all.
- **Staleness** is the other blind spot. The reply carries a `staleness` key only when the index is stale. A file added after the last build is not in the index, and the reply will not say so unless the index reports it stale. Check `target` and `staleness` before trusting a miss.

**Practical rule.** Treat a definitive empty as "the indexed symbols, docs and config of this target do not contain it." Treat anything else as "not looked, or not able to look." If the question is about a file type or corpus named in `not_indexed` or `not_searched`, read the source with Grep or Glob instead of trusting the index.