**Short answer:** the reply separates the two cases by grading the empty result, not by using one fixed sentence. A "definitive" negative is only issued after the index has been checked for rows the search did not read. Confidence is high for "not in the searched corpora of this index" and lower for "not in the repository," which the code itself does not claim.

I read `clew/mcp_server/emptiness.py`, `clew/cli.py` (`_not_indexed_scope`), `clew/query/corpus.py`, `clew/query/models.py`, and the tests `test_emptiness.py` and `test_not_indexed_report.py`. I did not run a query against a live index.

**How an empty `search` is graded**

| Case | Reply wording | Confidence it earns |
|---|---|---|
| One token, no hits in any searched corpus, no hits in unread corpora, file docs present | "This IS a definitive empty result… Do not retry" | High, but only for the searched corpora: names and `@brief`, macros, class/struct/union, gated config symbols, file docs |
| One token, but unread corpora hold matches (for example markdown or Kconfig prose) | "NOT DEFINITIVE — this index HOLDS matching rows that search does not read: N kind", with `unsearched_corpus_hits` in the payload | None for absence. The name exists; the reply points to `dossier` or `search(corpus='prose')` |
| One token, index built without file docs | "NOT definitive"; advises a rebuild | None for absence |
| Several tokens (conjunction) | "NOT definitive"; per-token counts in `token_hits`. If a token has zero hits alone, it says to retry without it. Otherwise it says to retry with fewer tokens | Only the diagnosis is solid. Absence is not claimed |

The grading runs in a fixed order, most specific first. A row in an unread corpus outranks the index-level advice, so a caller is not sent to rebuild when the real answer is "use dossier."

**Where "I did not look there" is answered**

The `scope` block in the payload says what the index covers: `source`, `file_count`, `top_levels`, and `extensions`. The derivation paragraph is removed from per-query replies and kept in `status`.

`not_indexed` and `not_indexed_count` come from the build, not from a query-time walk. The build compares the files it scanned against the `path` rows it wrote, and stamps the file types with no rows, for example `.sh=3, .yml=1`. The name list is capped at 12 entries; the count is exact.

Absence of the key means "not recorded," not "nothing missed." An index built before this stamp, or a build that never walked a tree (a rustdoc-only build), shows no `not_indexed` at all. A zero-count stamp is also omitted. The code is deliberate about this: an empty list would read as a claim the build never made.

**Caveats I found**

- The not-indexed check is stamped at build time. If files change after the build, the report describes the old tree.
- The comparison is at file level: a file is "indexed" if it has a `path` row. The test suite describes a case where a shell grammar is missing and files "carry no symbols." If those files still get `path` rows, the report would not flag them. I did not verify whether that happens, and it is the first thing to check if an empty answer about a script looks wrong.
- The "definitive" wording does not mean the symbol is absent from the repository. It means absent from the searched corpora, given the file-type scope recorded at build time. A caller who sees "definitive" with a `not_indexed` entry for the relevant extension should read the file directly, not trust the negative.