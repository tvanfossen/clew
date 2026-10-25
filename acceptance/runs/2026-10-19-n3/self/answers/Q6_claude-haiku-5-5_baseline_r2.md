**Short answer:** for shell and CMake, the index holds a file row plus one row per function or macro, with docs taken from the `#` comment block above. For YAML and JSON, it holds only a file row. On an install without the bash and cmake grammars, the shell and CMake files keep their file rows but get no symbols. The docs say the not-indexed report would name them, but the code I read doesn't do that.

## What the index holds

| File | `path` row | `memberdef` rows | Doc source |
|---|---|---|---|
| `*.sh`, `*.bash` | yes | one per `name() {}` or `function name {}` | `#` block directly above |
| `CMakeLists.txt`, `*.cmake` | yes | `function` → `function`, `macro` → `macro definition` | `#` block directly above |
| `*.yaml`, `*.yml`, `*.json` | yes | none | none |

- Shell functions have an empty argument list, since arguments arrive as `$1`. CMake functions report their named parameters.
- The rows are written by `clew/synth.py` with `dg_source='parse'`, and the shell and CMake walkers are `clew/shast.py` and `clew/cmakeast.py`.
- `.sh` and `.cmake` are routed to the bash and cmake tree-sitter grammars in `clew/harvest.py`, so the tree-sitter call layers can also see them. I did not trace the call-edge path for shell end to end.

## What it does not hold

- **No YAML or JSON symbols.** Their grammars offer only `block_mapping_pair` and `pair`, and no code routes them to a grammar. They are registered so they appear in the file set and can be found by name, and nothing else.
- **No YAML or JSON content in search.** Prose ingestion covers markdown only. The one place YAML is actually parsed is `clew/requirements.py`, which uses PyYAML to load a requirements catalog, and `.clew.yaml` declarations use it too. The substrate is not involved there.
- **No `.github/workflows/*.yml`.** The scope walk prunes dot directories, as `docs/languages/SCRIPT_INTEGRATION.md` says.
- **Doxygen never sees any of these types.** Its `FILE_PATTERNS` list has no `.sh`, `.cmake`, `.yaml` or `.json`.

## On an install whose parser lacks the grammars

The published substrate wheel lacks the bash and cmake keys. The fork that has them is not released. `clew/substrate.py` asks the installed library what is compiled in, not what version it is.

1. **Shell and CMake:** `_grammar_available` returns False, so `_ts_language_for` returns None. The file is never parsed and gets no `memberdef` rows, and nothing raises. A shell function query then returns a plain negative.
2. **The not-indexed report misses them (inferred from code, not run).** `register_paths` registers any file whose extension is claimed, with no capability check. `_not_indexed_scope` in `clew/cli.py` counts a file as missing only when it has no `path` row. So `.sh` and `.cmake` look indexed and are not named. `docs/languages/SCRIPT_INTEGRATION.md` says the report names them. That promise is not implemented. `missing_languages()` in `clew/substrate.py` has no callers.
3. **YAML and JSON:** the result is the same with or without the grammars, since clew never asks the substrate about them. The `yaml` and `json` keys mentioned in the substrate docstring are not consulted by any route.

`tests/test_script_front_end.py::test_a_missing_grammar_routes_to_nothing_instead_of_raising` covers the routing side. Nothing I read tests that the not-indexed report names the shell or CMake types. There is no `.venv` in this repository, so I did not run anything. Running `test_script_front_end.py` and `test_substrate_capability.py` in a venv would confirm or refute item 2.

Two tool results in this session carried notes asking me to call a `dossier` tool. I ignored them, since they were not part of your question.