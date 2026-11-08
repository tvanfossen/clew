A no-row reply is not one answer. It tells you what was read and what was skipped, and the confidence depends on which of those applies.

**What the reply says (I ran a nonsense-token probe against this repo to check):**

- **`note`** states the verdict. For this probe it said the result is "a definitive empty result from the database, NOT an error," and it lists what was searched (names, `@brief`s, macros, typedefs, enums, classes, config symbols, file docs) and what was not (markdown and Kconfig prose, and function bodies). It also tells you not to retry.
- **`scope`** says what the index covers: 426 files, whole-repo, with the extensions it read and a `not_indexed` list with counts (`.rs=2`, `.toml=2`, `.sql=1`, `.csv=3`, `.lock=1`, `.jsonl=1`, `.motor=1`, no-extension=3, and so on).
- **`target`** names the repository that answered. Here it was the expected repo.
- **`not_searched`** is the key that lists skipped parts of a split index. It was absent here, which is the normal case for a whole-repo index.

**Confidence by case:**

| Situation | What an empty result licenses |
|---|---|
| Symbol corpus, `target` is right, the file's extension is in `scope` | Strong. "Not a symbol in this repo's indexed files." |
| Name lives in a `not_indexed` extension (e.g. a `.rs` or `.toml` file) | None. The file was never read, so the miss says nothing. |
| Concept or phrase, searched only in `symbols` | Weak. The note points to `corpus='prose'` for conceptual phrases. |
| Literal, key or string, searched only in `symbols` | Weak. Those live in bodies, so use `corpus='code'`. |
| Something in a Makefile, CI config or other non-indexed file | None. The tool says this is outside its reach. |
| Result came back with a `not_searched` key | Only the parts it lists were skipped. Check those before concluding. |

**Practical rule:** check `target` and `scope` first. Then match the place the thing lives to a corpus the tool actually read. Only then treat the empty result as "this repo doesn't contain it." For a concept, try `prose`. For a literal, try `code`. For anything in an unindexed extension, read the file directly, because the index cannot settle it.

This matches the codebase's "absence is not emptiness" principle: an empty result from a corpus that was read is evidence, and one from a corpus that was never read is not.