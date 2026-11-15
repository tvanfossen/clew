An empty `search` reply is not a bare "no rows." It is built to separate "looked and found nothing" from "did not look," but the second case is spread across several fields, so you have to read them.

**What the reply says on a miss**

For my probe (`zzqxnonexistentsymbol`) the reply had `count: 0` and `results: []`, plus:

- **`note`**: states this is a definitive empty result, not an error or a malformed call, and tells the caller not to retry or guess. It also lists what was searched (names, `@brief`s, macros, typedefs, enums, classes, config symbols, file docs) and what was not: markdown/Kconfig prose, which needs `corpus='prose'`, and function bodies, which need `corpus='code'`.
- **`scope`**: `source: whole-repo`, 426 indexed files, the top-level directories, the extensions that were indexed, and `not_indexed`, which lists extensions the index skipped with counts (`.rs=2`, `.toml=2`, `.sql=1`, `.lock=1`, `.csv=3`, no-extension=3, and others).
- **`target`**: the repository that answered. An empty result from the wrong repository tells you nothing.

**Reading the two cases**

| Situation | How the reply shows it | Confidence in "not present" |
|---|---|---|
| Name absent from indexed symbol names and docs, in an indexed extension | `count: 0`, `note` says definitive | High, for the symbols corpus only |
| Term only in prose, or only in a function body | Same empty result; the `note` names the corpus it did not search | None until you run `prose` or `code` |
| Term in a file whose extension is in `not_indexed` | Same empty result; `scope.not_indexed` is the only hint | None; the file was never read |
| Wrong or unrelated `target` | `target` shows which repo answered | Not applicable; the answer is about a different repo |
| Split repository, with some parts not read | `not_searched` names the parts | None for the unread parts |

**How much confidence each answer gets**

- A zero from the symbols corpus over indexed extensions is strong evidence the repository has no such named thing. The `note` is written as a definitive database answer.
- The word "whole-repo" in `scope` overstates coverage. This repository has files in extensions the index does not read, so a symbol in a `.rs` or `.toml` file would also return zero with no error.
- The tool does not claim the miss is global. It only claims the searched corpus was searched. Before you conclude "not in this repository," check the `note`'s NOT-searched list, `scope.not_indexed`, `target`, and `not_searched`, then run the other corpora or read the uncovered files directly.

This matches the repo's own rule in AGENTS.md, "Absence is not emptiness": an empty result means "we looked," while a missing key or layer means "this never ran." Reading the `scope` and `note` fields is how you tell which one you have.