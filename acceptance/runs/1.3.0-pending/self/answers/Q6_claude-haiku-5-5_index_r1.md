**Short answer:** for shell and CMake the index holds definitions. For YAML and JSON it holds only the file's existence and name. On an installation without the grammars, the code I read does not do what the design docs say. The miss report would likely stay silent about the shell and CMake files it was built to name.

## What is held

| File type | Rows written | Symbols? | Notes |
|---|---|---|---|
| `.sh`, `.bash` | `path` + `memberdef` | Yes | Only `name() { }` and `function name { }`. No parameter list, so `args` is empty. |
| `.cmake`, `CMakeLists.txt` | `path` + `memberdef` | Yes | `function` and `macro` are kept distinct, since a macro pastes into the caller's scope. |
| `.yaml`, `.yml`, `.json` | `path` only | No | Present in the file set and findable by name. Their keys and values are not indexed. |
| `.md` | none here | No | Prose goes to the FTS index via `prose.py`. |

Shell and CMake definitions are documented from the `#` block immediately above them. Blank-line separation means no doc. The stage is `_ScriptSymbolHarvester` (`clew/synth.py:138`), which dispatches by node shape to `shast.py` or `cmakeast.py`. The rows are written in doxygen's shape, so downstream stages run on them unchanged.

**Not held:** shell variables and top-level commands, CMake targets, `option()`s and `set()`s (only function and macro definitions are harvested), and any YAML or JSON content. Shell and CMake call edges depend on these `memberdef` rows, so anything not harvested is also absent from the call graph. I read the walker docs and did not run a query to confirm the exclusion list.

## On an installation without the grammars

The docs in `clew/substrate.py` and `tests/test_not_indexed_report.py` say the front ends register nothing and the miss report names the missing file types. The code does not do that:

1. `register_synth_paths(output, scanned)` runs unconditionally (`clew/cli.py:1909`). `claims()` (`clew/synth.py:191`) checks only the extension, never `has_language`. So `.sh`, `.cmake`, `CMakeLists.txt`, `.yaml` and `.json` all get `path` rows whether or not the grammar exists.
2. The grammar gate is only in the parse route. `bash` and `cmake` are in `_OPTIONAL_KEYS` (`clew/harvest.py:145`), so a missing grammar yields no payload and no `memberdef`. Nothing errors.
3. `_not_indexed_scope` (`clew/cli.py:2646`) reports a file as missed only when it is absent from the `path WHERE type = 1` set. The shell and CMake files are in that set, so they are never named.

**Result:** on a grammar-less install, a query about a deploy script returns empty, the not-indexed block does not name the `.sh` files, and the caller reads absence where the truth is "not read". That is the failure the not-indexed report exists to prevent.

For YAML and JSON the outcome is benign. They are never harvested, so no grammar is requested and nothing crashes. They are also not in `_OPTIONAL_KEYS`, so `_grammar_available` returns True for them, which is harmless only because nothing routes to them.

**Verification gap:** this run directory has no `.venv`, so I could not execute a grammar-less build. The finding comes from reading the code. A RED test would settle it: monkeypatch `compiled_languages()` to an empty set, build a tree with one `.sh`, and assert the `.sh` appears in `not_indexed`. I expect it to fail.

**Suggested fix:** either gate the script-type claims on `has_language` so unreadable files get no `path` row and the miss report catches them, or have `_not_indexed_scope` also count script files that produced zero `memberdef` rows. The first is simpler but changes what the file set publishes. I have not changed any code. Should I write the RED test first?