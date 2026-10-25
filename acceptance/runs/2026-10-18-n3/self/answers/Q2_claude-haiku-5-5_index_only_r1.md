An empty search reply does not on its own say "absent." It carries a `note` and a `scope` block that together say what was and wasn't read, and the confidence depends on which of those applies.

**What I got from a live search** (`zzqvxnonexistentsymbol`, whole-repo, 426 files):

- `count: 0` with a `note` that calls it "a definitive empty result from the database, NOT an error," and tells the caller not to retry.
- The note lists what was searched: names and `@brief` of functions, variables, macros, typedefs, enums, enum values, macro expansions, classes/structs/unions, the config symbols the repo gates on, and file docs.
- It lists what was **not** searched: markdown and Kconfig prose. Those live behind `search(corpus='prose')`, where a conceptual phrase often matches.
- `scope` names the covered shape: the file count, top-level directories, indexed extensions, and a `not_indexed` list (for example `.rs=2`, `.toml=2`, `.sql=1`, `.lock=1`, and 14 extension groups in total).
- `target` names the repository that answered. Here it is the expected repo root.

**How the cases separate**

| Situation | What the reply shows | Confidence it's absent |
|---|---|---|
| Symbol-kind search, name not in indexed symbols, `target` correct | Definitive note, empty results | High for "no indexed symbol of that name." Not "absent from the repo." |
| Concept or phrase living in markdown/Kconfig prose | Note says prose was not searched | None from this search. Re-run with `corpus='prose'`. |
| File type in `not_indexed` (e.g. `.toml`, `.rs`, `.sql`) | Listed in `scope.not_indexed` | None. The file exists but was never read. |
| Build or CI config (Makefile, CI YAML) | Outside the indexed file set | None. Read the file directly. |
| Wrong `target`, or a split repo with vendored parts | `target` / `sub_index` / `not_searched` differs from the repo you meant | None until you query the right target or sub-index. |
| Multi-token query | Per the tool contract, the miss names the token that emptied the conjunction | Good for locating which term failed. Not verified here. |
| `staleness` block present | Index older than source | Low until `index(action='refresh')`. A newly added symbol may be missing. |

**Practical reading**

- Trust "no such symbol" only after checking `target`, that no `staleness` block is present, and that the name's kind is in the searched list.
- Treat any concept-level miss as unsearched until the prose corpus has been checked too.
- Anything in `not_indexed` or outside the file set is outside the index's reach. Grep or read it directly.