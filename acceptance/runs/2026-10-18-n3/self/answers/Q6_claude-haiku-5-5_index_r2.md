**Short answer:** the index holds *registrations* for YAML and JSON files, plus no symbols, call edges or bodies. Shell and CMake files get real function rows when their grammar is present. On an install without those grammars, shell and CMake fall back to registration only, but I found one gap in that fallback.

**What the index holds, by file type**

| Type | Path row (file set) | Symbols / bodies | Call edges | Source |
|---|---|---|---|---|
| `.sh`, `.bash`, `.cmake`, `CMakeLists.txt` | yes | yes, when the grammar is available | yes | `clew/synth.py:60-69`, `clew/shast.py`, `clew/cmakeast.py` |
| `.yaml`, `.yml`, `.json` | yes | never | never | `clew/synth.py:71-80` |

- **Shell and CMake:** the parse-built front end (`clew/synth.py`) writes `memberdef` rows for shell functions and CMake functions and macros. CMake macros map to doxygen's "macro definition" kind (`synth.py:98`).
- **YAML and JSON:** the front end registers them as `path` rows so they are in the file set and can be found by name. The comment at `synth.py:71-75` says the grammars offer only `block_mapping_pair` and `pair`, so no function concept exists. They are deliberately never harvested, which keeps every `steps:` key out of the function namespace.
- **Markdown** is excluded on purpose. `clew/prose.py` chunks it into the full-text index instead.

The index's own corpus confirms the boundary. A search for `yaml`, `cmake` and `.github` in the indexed-files corpus returned nothing (`search corpus=files`). That corpus only lists source files that have symbols or bodies, so the empty result is expected for data files and does not prove they are absent from the file set. The `.clew.yaml` and `requirements.yaml` that this repo declares are not visible in that corpus either.

**What it does not hold**

- Nothing from YAML or JSON content: no keys, no values, no schema meaning. `requirements.yaml` feeds the requirement layer through the guard's catalog reader, not through the parse-built front end.
- No call edges for any script. A shell script that calls another shell function, or a CMake `target_link_libraries`, is not linked.
- Anything outside the declared scope. The `scope` in `.clew.yaml` decides what is walked at all.

**Installation without the grammars**

- **YAML and JSON:** no change. Their registration never asks for a grammar, and they were never harvested, so a published-wheel install loses nothing it had.
- **Shell and CMake:** `clew/harvest.py:137-145` lists `bash` and `cmake` as optional keys. `_grammar_available` returns False, so `_ts_language_for` returns None and the file is never parsed. The result is no symbols and no call edges for those files. `clew/substrate.py:4-20` says the front ends "register nothing" and the miss report names the types as not indexed.
- **The gap:** I read `claims()` and `register_paths()` (`synth.py:191-226`) and found no capability check. `register_paths` is called unconditionally from `clew/cli.py:1911`. So on a grammarless install, `.sh` and `.cmake` files still get `path` rows. `_not_indexed_scope` (`cli.py:2646`) decides "missing" by checking the `path` table, so those files would not appear in the not-indexed report. The docstring and `tests/test_substrate_capability.py` describe the opposite. The existing not-indexed tests seed the `path` table by hand, so they never exercise this path.

I did not run this. The repo has no `.venv`, so I could not probe a real grammarless substrate. The gap comes from reading the code. The test to settle it would be a run of `register_paths` and `_not_indexed_scope` against a `compiled_languages()` that omits `bash` and `cmake`. If that confirms it, the fix is to gate the script claim in `register_paths` on `substrate.has_language` for `bash` and `cmake`, so the miss report names the files.