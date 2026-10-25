**Short answer:** the index holds a file-level row for every YAML and JSON file, and symbol rows for shell and CMake files when the parser has their grammars. It holds no symbols or call edges for YAML or JSON. On an installation whose substrate lacks the shell or CMake grammars, those files are silently left without symbols, and the index does not say so per file. I answered from the index's own documentation and symbol bodies, so these are the repository's claims about itself, checked only where I read the code bodies.

**What the index holds**

| Type | Row produced | Symbols | Mechanism |
|---|---|---|---|
| Shell (`.sh`, `.bash`, and `scripts/lib.bash`-style names) | `path` row plus function rows | Yes, `deploy() {…}` and `function rollback {…}` become function `memberdef` rows | tree-sitter `bash` grammar via `_TS_GRAMMARS` (`substrate:bash`) |
| CMake (`CMakeLists.txt`, `.cmake`) | `path` row plus function/macro rows | Yes, `function(add_firmware NAME)` becomes a function row with `argsstring` `(NAME)` | `substrate:cmake` grammar, with the file name matched directly in `SCRIPT_NAMES` |
| YAML (`.yaml`, `.yml`) | `path` row only | No | `claims()` in `clew/synth.py` registers the type so the file is in the file set |
| JSON (`.json`) | `path` row only | No | Same as YAML |

The index also holds the front-end contract: `claims()` puts `.sh`, CMake, YAML and JSON files into the file set, and rejects `src/main.c` and `README.md`. A test asserts that YAML and JSON files produce `path` rows and zero `memberdef` rows. YAML is claimed "so that it is in the file set, and harvested by nothing."

**What it does not hold**

- No symbols from YAML or JSON. Configuration keys, workflow steps and JSON objects are not rows.
- No call edges or lock or thread facts from any of the four types. The SCRIPT_INTEGRATION doc and `clew/synth.py` describe these files as having no harvest, call edges or symbols.
- No content search beyond the `path` row. The `search` corpus `files` only lists indexed source files, so YAML and JSON are absent from it by construction.
- Shell and CMake have no lock or thread layer. Their symbol rows are the only structure they get.

**On an installation whose parser lacks the grammars**

- The repository's test `tests/test_substrate_capability.py` says bash, cmake, yaml, json and markdown are registered in a fork of lang-parsing-substrate, "open upstream as PR #1 and not yet" merged. A stock substrate build therefore lacks them.
- `_OPTIONAL_KEYS` in `clew/harvest.py` is `{"bash", "cmake"}`. `_grammar_available` returns False for those when the substrate lacks them, and `_ts_language_for` then returns `None`. A test named `test_a_missing_grammar_routes_to_nothing_instead_of_raising` covers this path. So shell and CMake files silently get no symbols and no error.
- Other grammars (C, C++, Python, Rust, JS, TS) are not optional. `_grammar_available` returns True for them without measuring, so a missing one would not be caught there. The index does not say what happens then.
- The not-indexed report (`tests/test_not_indexed_report.py`) states that the index "reads shell and CMake, and registers YAML and JSON, but that depends on the installed substrate." So on a stock install the report cannot be relied on to name these files as "read."
- One documentation string in `tests/test_script_front_end.py` mentions an `unknown language key` error for a grammar the installed wheel lacks, and that a `.sh` file "routed to a bash grammar" would fail. That conflicts with the silent-drop behaviour above. I could not resolve which path raises the error and which drops silently from the index alone. Reading the test bodies and `clew/substrate.py` would settle it.