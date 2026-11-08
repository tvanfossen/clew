The reply separates the two cases with a `scope` block and a `note`, and the note is what tells you which kind of empty you have.

**What the reply says for a miss.** My probe for a nonexistent name returned `count: 0` and a note stating it "IS a definitive empty result from the database, NOT an error." The note then lists what was searched (names plus `@brief` of functions, variables, macros, typedefs, enums, classes and structs, config symbols, and file docs) and what was not (markdown and Kconfig prose, which needs `corpus='prose'`). The `scope` block gives the file count (426), the top-level directories, the extensions indexed, and a `not_indexed` list with counts. In this repo that list covers `.rs`, `.toml`, `.sql`, `.csv`, `.lock`, `.motor`, `.jsonl` and extensionless files.

**Confidence for each answer:**

| Reply says | What it licenses | Confidence |
|---|---|---|
| `count: 0`, name absent from searched kinds, extension in `scope.extensions` | The indexed source has no symbol of that name or brief. | High for that corpus. It is a database lookup, not a guess. |
| Concept lives in markdown or Kconfig prose | The symbol corpus cannot answer. Run `corpus='prose'`. | None for the symbol corpus, since the reply says it was never searched. |
| File extension appears in `scope.not_indexed` | The file was never read. Any "not found" for code in those files is meaningless. | Zero. Grep or read those files directly. |
| Target differs from the repo you mean | You queried a different index. | Check `target` first. |

So "the repository does not contain that" is only supported for the searched kinds and indexed extensions. "I did not look there" is what the `not_indexed` and prose notes report, and the reply names the place rather than leaving you to guess.

**What I did not verify.** I did not run a prose query to confirm that a conceptual phrase lands there. I did not test the multi-token conjunction behaviour that the tool description promises, where the reply names the token that emptied the match. I also did not read the grading code; the account above comes from the reply text, the `scope` block and the tool description. A grep for `not_searched` in the repo returned test files, which suggests the reporting is tested, but I did not open them.