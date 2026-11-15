**Short answer:** for shell and CMake, the index holds named definitions with their `#` doc blocks. For YAML and JSON it holds only the file's existence and name. On an installation without the bash and cmake grammars, shell and CMake fall back to path-only rows with no error. The docs say the miss report names those types, but the code I read does not support that.

This is from reading the code, not from running an index build.

**What the index holds, with the grammars present**

| File | Rows | Source |
|---|---|---|
| `*.sh`, `*.bash` | `path` row, plus `memberdef` per function (`name() {}` and `function name {}`) | `clew/shast.py`, `clew/synth.py:136-175` |
| `*.cmake`, `CMakeLists.txt` | `path` row, plus `memberdef` per `function()` (named params in `argsstring`) and per `macro()` (kind `macro definition`) | `clew/cmakeast.py`, `clew/synth.py:89-92` |
| `*.yaml`, `*.yml`, `*.json` | `path` row only, no symbols | `clew/synth.py:71-80`, `DATA_EXTS` |

- Doc text for shell and CMake comes from the `#` block immediately above a definition. A blank line detaches it, and a shebang stops the block. See `clew/synth.py` and `docs/languages/SCRIPT_INTEGRATION.md`.
- Rows are stamped `dg_source='parse'`.
- YAML and JSON are deliberately not harvested. Keys such as `steps:` would flood the function namespace. The design is that they are findable by name and appear in the file set.

**What the index does not hold**

- Anything that is not a function or macro definition in shell or CMake: top-level statements, variable assignments, `set()`, `target_link_libraries()`. I found no harvester that records these.
- The content of YAML or JSON. I found no full-text corpus for them. The prose corpus is markdown only (`clew/synth.py:78-79`, `clew/prose.py`).
- `.github/workflows/*.yml`. The scope walk prunes dot directories, so CI workflows are out of scope on every tier (`docs/languages/SCRIPT_INTEGRATION.md`, "Scope note").
- Shell or CMake call edges. I only saw definition harvesting for these languages. I did not verify call-edge coverage, so treat it as absent until checked.

**On an installation whose substrate lacks the grammars**

- `clew/substrate.py` asks the installed substrate what is compiled in, rather than comparing version strings.
- The router in `clew/harvest.py:203-225` returns no grammar for `.sh` and CMake, so no tree is parsed and no `memberdef` rows are written. Nothing raises. `tests/test_script_front_end.py:128-141` pins this.
- `register_paths` (`clew/synth.py:~190`, called from `clew/cli.py:1911`) claims files by extension and does not check the substrate. So shell, CMake and YAML/JSON files still get `path` rows and remain in the file set. The result is a file-set entry with no symbols.
- YAML and JSON behave identically on both installs, since they never had a grammar route.

**Discrepancy: the not-indexed report**

`SCRIPT_INTEGRATION.md` says a grammarless build's not-indexed report "names those file types". The code does not do that. `_not_indexed_scope` (`clew/cli.py:2646-2670`) lists only in-scope files that lack a `path` row. Because `register_paths` gives every such file a `path` row, a grammarless install would report nothing for `.sh` or `.cmake`. The test that looks like it covers this (`tests/test_not_indexed_report.py`) builds synthetic data without `path` rows, so it does not exercise the substrate-missing case.

The gap is that a grammarless install yields silent empty answers for shell and CMake, which the not-indexed report is meant to prevent. Either `register_paths` should skip claimed types whose grammar is absent, or `_not_indexed_scope` should also flag files that have a `path` row but no harvested rows for a grammar-backed type. A test on a substrate without `bash` and `cmake` would settle which behaviour is current.