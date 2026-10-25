**Short answer:** For shell and CMake, the index holds definitions (functions, and CMake functions and macros) only when the installed parser has those grammars. For YAML and JSON, it holds only the file's presence in the file set. On an install without the grammars, shell and CMake silently produce nothing except an error log, and the test suite skips rather than fails. I could not confirm from the index whether the missing-grammar case also leaves a visible "not indexed" marker for those files.

**What the index holds**

- **Claimed file types.** `claims()` in `clew/synth.py` (line 191) accepts `.sh`, `.bash`, `.cmake`, YAML and JSON. `CMakeLists.txt` is claimed by exact file name, not by its `.txt` extension, so `notes.txt` is not claimed. `tests/test_script_front_end.py` asserts this for `scripts/deploy.sh`, `scripts/lib.bash`, `CMakeLists.txt`, `cmake/toolchain.cmake`, `config.yaml`, `.github/workflows/ci.yml` and `data.json`.
- **Path rows.** `register_paths()` (`clew/synth.py:219`) writes a `path` row for every claimed file. It does not check the grammar. YAML and JSON stop here.
- **Definitions, shell and CMake only.** `_ScriptSymbolHarvester` (`clew/synth.py:138`) harvests shell functions and CMake `function` and `macro` definitions. The test `test_shell_and_cmake_definitions_become_rows` expects `deploy` (function), `add_firmware` (function) and `strict_warnings` (macro definition). Shell and CMake are parsed through `clew/shast.py` and `clew/cmakeast.py`, which share `clew/scriptast.py`. Those rows carry the `#` doc block.

**What it does not hold**

| File type | Path row | Symbols | Call edges |
|---|---|---|---|
| Shell (`.sh`, `.bash`) | yes | functions, with a grammar | not established |
| CMake (`.cmake`, `CMakeLists.txt`) | yes | functions and macros, with a grammar | not established |
| YAML, JSON | yes | none, by design | none |

- `test_the_data_files_are_in_the_file_set_with_no_symbols` asserts that YAML and JSON produce no member rows. `claims()`'s docstring says a YAML file is "harvested by nothing."
- YAML is read as input, not as symbol-bearing source. `ingest_requirements_yaml`, the data-model manifest loader and the `.clew.yaml` declaration loader all parse YAML. The index uses YAML as configuration and does not turn the repo's own YAML files into symbols.
- The `files` corpus only lists indexed source files, so a YAML path row does not appear there. A search for `yaml` in that corpus returned nothing.
- Shell and CMake files have no doc block or body in the index unless the grammar is present. I did not confirm that call edges exist for them.

**Installation without the grammars**

- `compiled_languages()` (`clew/substrate.py:39`) returns an empty set when `lang_parsing_substrate` cannot be imported or reports no languages. It logs at ERROR, not DEBUG, because the project treats a silent empty index as the failure to avoid.
- `has_language()` and `missing_languages()` (`clew/substrate.py:62` and `:72`) report which keys are absent, in the caller's order.
- The shell/CMake end-to-end test calls `missing_languages(("bash", "cmake"))` and calls `pytest.skip` with a message naming the missing languages. On such an install the test is skipped, not failed.
- YAML and JSON are unaffected by grammar absence, because they never reach a parser.

**Not verified from the index**

- I could not confirm whether the build path calls `register_paths` or `emit_definitions` only when `has_language` is true. The dossiers show `emit_definitions` does not check it. So shell files probably still get path rows with no symbols.
- If so, `_not_indexed_scope` (`clew/cli.py:2646`) would not list `.sh` or `.cmake` as "not indexed," because it counts only files with no path row. That would be a silent gap. This is an inference, and I did not read a live build's `not_indexed` stamp to check it.
- The test file header and `tests/test_not_indexed_report.py` say shell and CMake are indexed "only when the grammar is present" and that a miss should name unread file types. I only saw the truncated briefs, so I did not confirm the full wording.

To settle the last point, run a build on an install without the grammars and check whether `not_indexed` names `.sh` and `.cmake`.