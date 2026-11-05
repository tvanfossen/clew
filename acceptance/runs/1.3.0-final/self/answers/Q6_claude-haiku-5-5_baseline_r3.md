**Short answer:** clew's index holds *definitions* from shell and CMake, and only *registration* for YAML and JSON. It holds no call edges for any of them and no keys or values from the data files. On an installation without the shell and CMake grammars, the gap is silent, and the not-indexed report does not name it. That contradicts what the repo's own docs promise.

## What the index holds

| File type | `path` row (file set) | `memberdef` rows | Doc source | Notes |
|---|---|---|---|---|
| `.sh` `.bash` | yes | one per `name() {}` or `function name {}` | the `#` block directly above, no blank line | `argsstring` is empty, since shell has no parameter list. `dg_source='parse'`. |
| `.cmake`, `CMakeLists.txt` | yes | one per `function()` (named params recorded) and `macro()` (kind `macro definition`) | the `#` block above | Only definitions are harvested. |
| `.yaml` `.yml` `.json` | yes | none | none | Registered and never harvested. |

The relevant code:
- `clew/synth.py:62-80` defines the claimed types, and `:71-80` documents the data files as registered but never harvested.
- `clew/shast.py` and `clew/cmakeast.py` export only `harvest_definitions`. Neither exports call harvesting, which JS/TS has in `jsast.py`.

**Not held:**
- Shell and CMake call sites, so no call edges from scripts.
- YAML and JSON keys, values, or structure. Their grammars offer `block_mapping_pair` and `pair`, which were deliberately not turned into symbols so that every `steps:` key does not pollute function lookups.
- Anything under dot-directories. `docs/languages/SCRIPT_INTEGRATION.md` says the scope walk prunes them, so `.github/workflows/*.yml` is out of scope. I did not verify this in the scope code.

## What happens when the grammars are missing

Only `bash` and `cmake` are optional. `harvest.py:145` (`_OPTIONAL_KEYS`) and `harvest.py:215-225` (`_grammar_available`) make a route to a missing grammar return `None`. The file is then not parsed and gets no symbols. Nothing raises, and nothing is logged.

Three things follow:

1. **The file still enters the file set.** `cli.py:1909` calls `register_synth_paths` unconditionally, and that function claims `.sh`, `.cmake` and the data types regardless of grammar availability. These files therefore look covered.
2. **The not-indexed report does not name them.** `cli.py:2646-2684` (`_not_indexed_scope`) computes "missing" as scanned files with no `path` row. Shell and CMake files have path rows, so they are never listed. The same applies to YAML and JSON. `SCRIPT_INTEGRATION.md` says the data files are "named by the not-indexed report when a query finds nothing". That is false in the code.
3. **The promised explanation does not exist.** `substrate.py` says a missing grammar "degrades with an explanation". `missing_languages()` has no production caller. Only the tests use it (`tests/test_substrate_capability.py`, `tests/test_script_front_end.py`). The only production caller of the capability check is the silent `_grammar_available`.

YAML and JSON are unaffected by a missing substrate grammar, because they never needed one. Their gap is the reporting issue above.

The code's own comments say the published `lang-parsing-substrate` 0.11.2 wheel lacks `bash` and `cmake`, and the grammars sit in an unreleased fork. So on a default install, shell and CMake probably produce no `memberdef` rows today. I could not confirm this here: the repo has no `.venv`, so I did not run `compiled_languages()`.

## Recommended fixes (not applied; this was a question)

- Have the not-indexed report consult `substrate.has_language` for `bash` and `cmake`, and name those extensions when the grammar is absent. This is the smallest change that makes the failure visible.
- Either make the data files a named category in the report, or stop claiming they are named there. They are visible by name, but the report cannot list them.
- Log once at build start when an optional grammar is missing, using the count of affected files. `substrate.py` already promises that and nothing implements it.