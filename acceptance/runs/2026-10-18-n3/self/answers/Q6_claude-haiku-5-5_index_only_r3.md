## Short answer

For shell, CMake, YAML and JSON, the index holds **a file-set entry for every such file, plus function-level definitions for shell and CMake only**. It holds no symbols, bodies, calls or structure for YAML and JSON. On an install whose parser lacks the bash or CMake grammar, those files silently lose their definitions and keep their file rows. A missing C or Python grammar is treated as a broken install and fails loudly.

## How it works

Doxygen reads none of these languages, so a separate front end in `clew/synth.py` handles them. Its selection function `claims()` is extension-based, and it registers matching files in the `path` table.

| File type | In the index | Symbols | Source |
|---|---|---|---|
| Shell (`.sh`, `.bash`, `deploy.sh`) | yes | function definitions, with `#` doc blocks | `clew/shast.py` via `_ScriptSymbolHarvester` |
| CMake (`CMakeLists.txt`, `*.cmake`) | yes | `function` and `macro` definitions (macros as "macro definition") | `clew/cmakeast.py`, `harvest_definitions` |
| YAML (`config.yaml`, `.github/workflows/ci.yml`) | yes, as a file | none | registered by `claims()`, "harvested by nothing" |
| JSON (`data.json`) | yes, as a file | none | same as YAML |

Two details matter:

- **CMake is matched by file name, not extension.** `CMakeLists.txt` routes, but a plain `.txt` does not. A `CMakeLists.txt` with no function definitions yields only its file row.
- **Shell and CMake definitions go through the same writer as JS/TS**, under a separate `script` key prefix, so they cannot collide with JS symbols at the same line.

## What the index does not hold

- **CMake build content.** `cmakeast.py` harvests only function and macro definitions. Targets, `add_executable`/`target_link_libraries` dependencies, compile flags and options are not recorded, even though the module's own docs say `CMakeLists.txt` is where a repo states what it builds.
- **YAML and JSON content of any kind.** The test `test_the_data_files_are_in_the_file_set_with_no_symbols` pins this: they are registered and carry no rows. CI workflows, `config.yaml` keys and `data.json` values are not searchable through the index.
- **Call edges, locks, threads or dataflow from shell or CMake.** I found no evidence of these; the script front end emits definitions only.
- **Shell and CMake bodies beyond definition records**, as far as the index shows.

I could not confirm whether this repository's own `.sh` or `.cmake` files are in scope. The index's scope summary lists `.c .cpp .h .json .md .py .yaml` as indexed extensions and does not list `.sh` or `.cmake`. Check `index(action='status')` on this target if that matters.

## An installation whose parser lacks the grammars

1. **Detection.** `compiled_languages()` in `clew/substrate.py` reads `lang_parsing_substrate.languages()`. If the package is missing or unreadable, it logs an ERROR ("reports no languages") and returns an empty set, not a silent fallback.
2. **Optional keys.** Only `bash` and `cmake` are optional (`_OPTIONAL_KEYS` in `clew/harvest.py`). `_grammar_available()` returns False for them when absent, and `_ts_language_for()` returns `None`. The test `test_a_missing_grammar_routes_to_nothing_instead_of_raising` pins this degrade.
3. **Result.** `claims()` does not consult grammars, so `register_paths` still inserts the `.sh` and `CMakeLists.txt` path rows. Their harvest then routes to nothing, so the file appears in the file set with zero definitions and no error at the file level.
4. **Always-present grammars are not gated.** C, C++ and Python are not in `_OPTIONAL_KEYS`. A wheel missing them is treated as a broken install, and failing loudly is the intended behaviour.
5. **YAML and JSON are not optional keys either.** The index does not say what happens if their grammars are missing. Since they carry no symbols, the effect should be nil, but I did not verify that.
6. **Tests skip, not fail.** `test_shell_and_cmake_definitions_become_rows` calls `pytest.skip("substrate lacks [...]")` when bash or cmake is absent. On such an install the suite reports a skip, not a failure, so CI can go green while the shell and CMake feature is off.

The substrate's own brief says the five configuration languages (bash, cmake, yaml, json, markdown) are registered in a fork of lang-parsing-substrate that is open upstream. I read that as meaning a stock upstream wheel may lack bash and CMake, but I did not confirm which wheels ship them, and I could not read the referenced `.claude/tmp/substrate-fork.md`.

A caveat on the answers: several dossiers reported `anchor_mismatch`, meaning the file changed since the index was built, for `build_harvest_plan`, `run_harvest` and the degrade test. Line numbers for those may be off, though the behaviour described matches their bodies.