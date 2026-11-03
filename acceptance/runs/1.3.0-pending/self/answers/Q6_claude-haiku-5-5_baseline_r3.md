**Short answer:** for YAML and JSON the index holds only that the file exists. For shell and CMake it holds each function and macro definition, but not the commands inside them. On an installation without the shell/CMake grammars, the code's own comments say those files appear in the not-indexed report, but the code does not do that. I could not run it here, so that last point rests on reading the code.

**What the index holds, by type** (from `clew/synth.py`, `shast.py`, `cmakeast.py`, `harvest.py`)

| File type | `path` row | Symbols (`memberdef`) | Notes |
|---|---|---|---|
| `.yaml`, `.yml`, `.json` | Yes | None, by design | Findable by name, counted in the file set. Never harvested. |
| `.sh`, `.bash` | Yes | One per `name() {…}` or `function name {…}` | Scope is dotted, e.g. `scripts.deploy.deploy`. No args, since shell passes arguments as `$1`. Brief comes from the `#` block directly above, and a blank line breaks the link. |
| `.cmake`, `CMakeLists.txt` | Yes | One per `function()` (kind `function`) and per `macro()` (kind `macro definition`) | Function arguments are the parameter list. Macros are recorded as macros because their variables leak into the caller. |

**What it does not hold**

- YAML and JSON content: no keys, values, CI jobs, or workflow steps. The only YAML semantics clew reads are its own `.clew.yaml` (scope, guard, dispatch), through separate config loaders, not through the index.
- Shell and CMake top-level commands: `set`, `export`, variable assignments, `add_executable`, `target_link_libraries`, `source` lines, and the commands in function bodies are not symbols.
- Anything in a file no grammar parsed: the `path` row exists, but there is no body, no refid, and no call data.
- I found no shell- or CMake-specific call-site walker (`call_edges.py`, `signature.py`, `reachability.py` don't mention bash or cmake). Whether calls *from* shell functions are recorded depends on the generic harvest, which I did not trace.

**Installation without the grammars**

- `substrate.py` says the gate is "what is compiled in". Against the published wheel, `bash` and `cmake` are absent. `harvest._ts_language_for` returns `None` for them, so no tree is parsed and no definitions are written. The test `test_the_data_files_are_in_the_file_set_with_no_symbols` covers the YAML/JSON case.
- **The problem:** `register_paths` in `synth.py` calls `claims()`, which tests extension and file name only. It never checks `has_language`. So `.sh`, `.cmake` and `CMakeLists.txt` still get `path` rows on a grammar-less install.
- `_not_indexed_scope` in `cli.py` decides what is "not indexed" by checking the `path` table. Those files are present there, so they are counted as covered. They are missing from the not-indexed report and no definitions are written. That is the silent empty answer the project's "absence is not emptiness" rule exists to prevent. It also contradicts the `substrate.py` docstring, which says the front ends "register nothing" and the miss report names these types.
- No test covers this. `test_script_front_end.py` checks only that `_ts_language_for` returns `None` when the grammar is absent.

**Suggested fix:** in `register_paths`, drop `.sh`, `.bash`, `.cmake` and `CMakeLists.txt` when `substrate.has_language("bash")` or `("cmake")` is false, so the miss report names them. Add a RED test that runs with those keys monkeypatched out and asserts the names appear in `not_indexed`. YAML and JSON should stay registered, since they never need a grammar.