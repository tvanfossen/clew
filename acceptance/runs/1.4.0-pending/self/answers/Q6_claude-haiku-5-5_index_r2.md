The short answer: for YAML and JSON the index holds only a file row, and for shell and CMake it holds real symbols, but only when the installed parser has those grammars. This repository itself has no shell or CMake files (a glob for `*.sh`, `*.bash`, `*.cmake` and `CMakeLists.txt` finds nothing), so none of the script paths are exercised here.

| File type | What the index holds | What it does not hold |
|---|---|---|
| `.sh`, `.bash`, `.cmake`, `CMakeLists.txt` | `memberdef` rows for functions and macros, with docs from the `#` block above the definition (`clew/synth.py`, `clew/shast.py`, `clew/cmakeast.py`). A CMake `macro` is recorded as `kind = 'macro definition'`. | Shell functions have empty `argsstring`; arguments arrive as `$1`/`$@`. Doxygen reads none of these. |
| `.yaml`, `.yml`, `.json` | A `path` row only. The file is in the file set, findable by name, and counted in coverage. | No symbols, by design: `block_mapping_pair` and `pair` would flood the namespace that answers `dossier("my_function")`. Coverage lists these files among the "barren" ones, so they look like gaps in the figure. |

Two more gaps. Dot directories are pruned from scope, so `.github/workflows/*.yml` is invisible on every tier. Separately, YAML data-model manifests are read by PyYAML in `clew/shared_key_edges.py`, not by tree-sitter, so their content reaches the declared-edge layer while the file itself carries no rows.

**On an install whose parser lacks the grammars:**

- Routing is capability-gated. `_ts_language_for` (`clew/harvest.py:184`) returns `None` when `_grammar_available` is false, and `test_a_missing_grammar_routes_to_nothing_instead_of_raising` pins that. The build does not crash; the file keeps its `path` row and gets no symbols.
- The docs say the not-indexed report then names those types so a miss tells the caller to read the file. I did not verify this. `_not_indexed` (`clew/query/corpus.py:326`) only splits a stamped string, and the path rows exist, so `.sh` may not appear in that report at all. Treat it as a claim to test.
- The published substrate wheel does not carry the `bash` and `cmake` grammars, according to `docs/languages/SCRIPT_INTEGRATION.md`. I could not check this install's grammars because this run directory has no `.venv`.
- If PyYAML is missing, `import_shared_key_edges_declared` (`clew/shared_key_edges.py:2075`) silently no-ops. A data-model YAML that is never read produces no declared edges and no warning, which is the "absence is not emptiness" failure the codebase warns about.