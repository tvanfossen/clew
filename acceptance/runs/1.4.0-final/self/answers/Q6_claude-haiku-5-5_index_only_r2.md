**Short answer:** for shell, CMake, YAML and JSON, the index holds the file's existence and location, plus symbol rows for shell functions and CMake functions/macros when the grammars are present. It holds nothing for YAML or JSON content, and it holds no call edges for any of them. On an install without the grammars, the index still registers the files, but the shell and CMake symbols disappear. Whether the miss report flags that is an inference I could not confirm from the index (details below).

**What the index holds**

| File type | Registered as a file (`path` row) | Symbols | Notes |
|---|---|---|---|
| `.sh`, `.bash` | Yes | Function definitions (`name() {}` and `function name {}`), with the `#` block above as the brief | Routed to the bash grammar (`clew/shast.py`) |
| `CMakeLists.txt`, `.cmake` | Yes | `function` and `macro` definitions, with `kind` recorded so a macro is not flattened into a function | Routed to the cmake grammar (`clew/cmakeast.py`). The name matches the whole filename, so a plain `.txt` is not claimed |
| `.yaml`, `.yml`, `.json` | Yes | None, by design | `DATA_EXTS` is "registered, never harvested" (`clew/synth.py`) |

Shell and CMake rows are written by `clew/synth.py` in doxygen's shape, so the query layer reads them like C rows. The stated reason YAML and JSON get no symbols is that their grammar nodes are keys (`block_mapping_pair`, `pair`). Writing them as `memberdef` rows would put every `steps:` key into the namespace that answers `dossier("my_function")`. They are findable by name and count toward the not-indexed report, but nothing about their contents enters the function namespace.

Separately from the front end, the index reads some YAML and JSON semantically. `.clew.yaml` is loaded as the repository's declaration, and its `guard:` section is read. `requirements.yaml` is ingested as a requirements catalog, and the `datamodel.py` manifests are read as key catalogs. These paths are distinct from the shell/CMake/YAML/JSON front end.

**What it does not hold**

- No symbols for YAML or JSON content, including workflow `jobs:`, `steps:` and JSON config keys.
- No call edges from or to shell or CMake, so the index cannot answer "what does `deploy.sh` call" or "which target links this library" as graph queries. The CMake dependency and flag content is also not parsed beyond definitions.
- No shell variables, sourced files, or CMake `set()`/`target_link_libraries()` facts. Only definitions are harvested.

**Installation without the grammars**

The published `lang-parsing-substrate` wheel lacks the five configuration keys, because the grammars are in an unreleased fork that reports the same version string. `clew/substrate.py` therefore asks what is compiled in, not what version is installed.

- `_OPTIONAL_KEYS` is `{bash, cmake}`. Those two routes check `_grammar_available` before parsing. If absent, `_ts_language_for` returns `None` and the file gets no symbols. It does not raise. Without this, `parse_tree` would raise `ValueError` mid-parse.
- A substrate that cannot be imported yields an empty language set and logs an error. It is not a crash.
- Shell and CMake files are still registered as files, so `dossier` and `search` can find them by name, but they have no `memberdef` rows.

**Open question: does the miss report fire?**

The substrate module's documentation says the miss report names shell, CMake, YAML and JSON as not indexed on a published wheel. But `claims()` is purely extension-based, and `register_paths` does not check the substrate, so those files would get `path` rows (`type=1`). `_not_indexed_scope` counts scanned files with no `path` row, so under that reading the report would be empty for these types. Either the report misses them on the published wheel, or `register_synth_paths` is gated somewhere the index did not show me. I could not settle this from the index. A build against the published wheel, followed by a check of the stamped `not_indexed` value, would settle it.