## Short answer

For shell, CMake, YAML and JSON, the index holds a file row, and for shell and CMake also function definitions. YAML and JSON contribute nothing about their contents unless a declared reader parses them. The one real gap is on an install whose parser lacks the bash or cmake grammar: those files can be silently absent from the symbol layer and are not reported as missing.

This repository has no `.sh`, `.bash`, `.cmake` or `CMakeLists.txt` files (Glob found none). So the shell/CMake half below comes from reading the code and its tests, not from this repo's data. The YAML and JSON files here are indexed as file rows with zero symbols.

## What the index holds

| File type | File row | Symbols | Grammar needed | Notes |
|---|---|---|---|---|
| `.sh`, `.bash` | yes | `memberdef` per function, brief from the `#` block above it | `bash` (optional) | `clew/synth.py:62`, `clew/harvest.py:98` |
| `.cmake`, `CMakeLists.txt` (by name) | yes | `memberdef` per function or macro, macros mapped to "macro definition" | `cmake` (optional) | `clew/synth.py:69`, `clew/harvest.py:99-105` |
| `.yaml`, `.yml`, `.json` | yes | none | none | Registered and never harvested (`clew/synth.py:71-80`) |

- Shell and CMake definitions are written with `dg_source='parse'`, so they are distinguishable from doxygen rows.
- YAML and JSON are in the file set and findable by name. The index does not hold their keys or structure as symbols.

## Where YAML and JSON content does enter the index

Content comes in only through specific readers that call `yaml.safe_load` or `json.loads` on a declared path, not through the grammar:

- `requirements.yaml` → requirement rows (`clew/requirements.py:365`). This is why this repo shows 152 requirements.
- `.clew.yaml` → declarations (`clew/declaration.py:418`).
- Data model, locks, threads, dispatch and shared-key sections, each read from their declared file.

A YAML or JSON file that no declaration points at contributes nothing beyond its file row.

## What the index does not hold

- No symbols, call edges or keys for any YAML or JSON file that is not a declared source.
- No structure of `.mcp.json` or `hooks/hooks.json`. `hooks.json` is a file row with zero symbols.
- Shell and CMake: only function and macro definitions. I did not verify whether call edges are produced for shell or CMake, so treat that as unknown.

## On an installation without the bash or cmake grammar

Only `bash` and `cmake` are treated as optional. For C, C++, Python, Rust, JS and TS a missing grammar is meant to fail loudly (`clew/harvest.py:137-144`).

When bash or cmake is absent:

1. `_ts_language_for` returns None for `.sh` or `.cmake` (`clew/harvest.py:203`). Nothing is parsed and no `memberdef` rows are written.
2. **The file still gets a `path` row.** `register_paths` claims by extension and name only and never checks the grammar (`clew/synth.py:226`). Because `_not_indexed_scope` reads the `path` table (`clew/cli.py:2673`), these files are counted as indexed. They do not appear in `not_indexed`, so the index reports nothing missing.
3. No log line is written on that route. `compiled_languages` logs an error only when the substrate import fails, not when it loads without bash (`clew/substrate.py:46-54`).
4. The bash and cmake tests skip when the grammar is missing (`tests/test_script_front_end.py:106,119,181,197`). On such an install the suite is green with no coverage of this path.

Result: a bash-less install shows `scripts/deploy.sh` as present with zero functions, and nothing says why. That violates the project's "absence is not emptiness" rule. This is from reading the code, not from running an install without the grammar.

## Suggested fix (not applied)

Gate script claims on `substrate.has_language` in `register_paths`, so unparsed `.sh` and `.cmake` files fall into `not_indexed` and the report names them. Add a logged warning when an optional grammar is missing. Un-skip the two grammar tests by making the grammar a declared install requirement, not a skip condition. I have not changed anything.