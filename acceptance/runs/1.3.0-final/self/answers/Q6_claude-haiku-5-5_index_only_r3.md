**Short answer:** for this repository the index holds shell functions and CMake functions and macros as symbols, and holds YAML and JSON files only as file-set entries with no symbols. It does not hold the build graph, the config keys, or the data contents. On an installation whose substrate lacks the grammars, the shell and CMake symbols go missing and the not-indexed report should say so. I could not confirm from the index that the YAML/JSON path rows are gated on the grammar, so treat that part as unverified.

**What the index holds**

- **Shell (`.sh`, `.bash`):** each function definition becomes a symbol, with its `#` comment block as the brief. Both function spellings are harvested, with line spans. A script that defines no function yields nothing.
- **CMake (`CMakeLists.txt`, `.cmake`):** `function()` and `macro()` definitions become symbols, with the `#` block above as the brief. A command-only CMake file yields no definitions. Targets, `add_executable`, variables, options and dependencies are not held.
- **YAML (`.yaml`, `.yml`) and JSON (`.json`):** the files are registered in the file set so they are findable by name. They carry no `memberdef` rows, no call edges and no symbols. `test_the_data_files_are_in_the_file_set_with_no_symbols` pins this.
- **Mechanism:** `clew/synth.py` (v2) writes these rows from the parse, after doxygen, in the same tables doxygen writes. Shell and CMake symbols are stamped as parse-sourced rows.

**What it does not hold**

- Anything inside a YAML or JSON file: keys, values, the contents of `.clew.yaml`, or CI workflows such as `.github/workflows/ci.yml`. The `search` corpus can find these files by name but cannot find their contents.
- CMake build semantics and shell call graphs beyond the definitions themselves.
- Doxygen does not read these files, so the index is the only place they appear. Reading the file directly is the correct fallback for anything else.

**On an installation without the grammars**

- The gate is `clew/substrate.py`. It asks the installed wheel which languages are compiled in, not what its version says. The published wheel reports the same version as the fork that carries these grammars, so a version check cannot tell them apart.
- With the grammars absent, `compiled_languages()` returns an empty set and logs an error. It does not crash. `missing_languages()` names what is absent.
- The only optional keys are `bash` and `cmake` (`_OPTIONAL_KEYS` in `clew/harvest.py`). `_grammar_available` checks them before routing a file to a grammar.
- The not-indexed report is stamped at build time. `test_not_indexed_report.py` describes the example: "14 `.sh` files were in scope and none of them are in this index." An empty answer then names the file types the build did not read, so it is not mistaken for absence. An index built before that release reports nothing rather than an invented empty set.
- Gap: `claims()` in `clew/synth.py` is a pure extension test and does not check `has_language`. That suggests `register_paths` would still write YAML and JSON path rows on a build without the grammars. The substrate docstring says the front ends register nothing in that case. I could not find the gating call from the index, so I cannot say which is true.

**Also in the index**

`clew/requirements.py` loads a target's `requirements.yaml` through a separate path, `ingest_requirements_yaml`. That is a separate reader, not the substrate grammar, and I did not check its dependencies.