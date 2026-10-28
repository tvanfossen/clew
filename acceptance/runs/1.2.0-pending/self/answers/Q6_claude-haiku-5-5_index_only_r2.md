**Short answer:** for shell and CMake, the index holds function and macro definitions with their `#` doc blocks. For YAML and JSON it holds only the file's existence and name. Nothing in those files becomes a symbol. On an install whose parser lacks the grammars, shell and CMake lose their definitions, but the index may not report that loss the way its design says it does.

**What the index holds**

| File type | Rows written | Source |
|---|---|---|
| `.sh`, `.bash` | `memberdef` rows for `name() {…}` and `function name {…}`, with the `#` block above as the brief. No parameter list, since arguments arrive as `$1`. | `clew/shast.py` |
| `CMakeLists.txt`, `.cmake` | `memberdef` rows for `function` and `macro`. A macro is recorded as a macro, because it leaks variables into the caller's scope. | `clew/cmakeast.py` |
| `.yaml`, `.yml`, `.json` | A `path` row only. No `memberdef`, no harvest, no symbols. | `clew/synth.py` (`DATA_EXTS`) |

The YAML and JSON choice is deliberate. Their grammars expose `block_mapping_pair` and `pair`, and turning those into rows would put every `steps:` key into the namespace that answers `dossier("my_function")`. The design goal is that these files are findable by name and named when a query misses.

**What it does not hold**

- YAML and JSON keys and values are not symbols.
- A CMake file that only calls commands yields no definitions, so `add_library`, `target_link_libraries` and similar calls are not held as rows. The test `test_a_cmake_file_that_only_calls_commands_defines_nothing` pins this.
- Shell has no parameter information, and no `shast` row says anything about variables or external commands.
- I could not confirm from the index whether call edges are built from shell or CMake bodies. The `memberdef` rows exist, so the call layer can resolve against them, but I found no evidence either way and would not claim it.
- Data files that clew reads for its own configuration (`.clew.yaml`, `requirements.yaml`, key lists, UDM manifests) go through separate parsers in `datamodel.py`, `requirements.py` and the guard config. Those reads are not symbols either.

**What happens without the grammars**

The substrate is the parser. Its published wheel reports the same version as the fork that carries the bash, cmake, yaml and json grammars, so clew checks for the grammars themselves through `substrate.has_language` (`clew/substrate.py`).

- The routing in `_ts_language_for` checks `_grammar_available`, and only `bash` and `cmake` are optional there (`_OPTIONAL_KEYS`). Without them, `.sh` and `CMakeLists.txt` route to `None`, so the file gets no symbols and the build does not crash. `test_a_missing_grammar_routes_to_nothing_instead_of_raising` pins this.
- YAML and JSON are not in `_TS_GRAMMARS` at all, so they are never parsed by tree-sitter whether or not the grammars are installed.
- The not-indexed report is supposed to name the file types a build had in scope but did not index. The test file's own description says a deploy-script query on the published wheel would come back empty and the report would name it.

**A likely gap in that report.** I inferred this from function bodies, not by running it. `register_synth_paths` inserts `path` rows for every file `claims()` accepts. `claims()` covers shell, CMake, YAML and JSON and is not gated on the substrate. `_not_indexed_scope` counts a file as indexed when it has a `type = 1` `path` row. So on a build whose parser lacks the shell grammar, a `.sh` file would have a path row, count as indexed, and be left out of `not_indexed`. The result would be an empty deploy-script answer with no statement that the file type was skipped. That contradicts the design described in `tests/test_not_indexed_report.py` and `clew/cli.py`. A test that builds against a substrate missing `bash` and checks `not_indexed` for a `.sh` file would settle it.