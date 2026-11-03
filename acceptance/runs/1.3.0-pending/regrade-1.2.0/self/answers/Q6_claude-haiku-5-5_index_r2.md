## Short answer

On this repo's index, shell, CMake, YAML and JSON are treated differently. Shell and CMake get function-level symbols. YAML and JSON get only a file-set entry, with no symbols. On an installation whose substrate lacks the grammars, shell and CMake symbols disappear, and the code I read does not show the "not indexed" report that the docs promise.

## What the index holds

| File type | Rows written | Source |
|---|---|---|
| `.sh`, `.bash` | `path` row, plus `memberdef` for each `name() {…}` or `function name {…}` | `clew/shast.py` |
| `CMakeLists.txt`, `.cmake` | `path` row, plus `memberdef` for each `function` and `macro`, with the macro recorded as a macro | `clew/cmakeast.py` |
| `.yaml`, `.yml`, `.json` | `path` row only | `clew/synth.py` `DATA_EXTS` |

- **Shell and CMake docs** come from the `#` block directly above a definition. A blank line between the block and the definition means no doc.
- **Shell** has no parameter list, so `args` is empty. That is the language's truth, not a gap.
- **Rows are stamped `dg_source='parse'`**, which marks them as written by the parse-built front end, not doxygen.
- **YAML and JSON are deliberately left without symbols.** The design comment in `tests/test_script_front_end.py` says that writing `steps:` or `runs-on:` keys as `memberdef` would flood the namespace that answers `dossier("my_function")`. They are findable by name through the file set.

## What it does not hold

- Shell top-level statements, variables and sourced files.
- CMake `set`, `target_*` calls, and targets as entities. Only `function` and `macro` definitions are harvested.
- Any YAML or JSON content. Keys, CI jobs and workflow steps are not queryable.
- I did not confirm whether shell or CMake call edges are produced. The docs describe the JS/TS call edges as a 1.1.0 addition, and I did not check the shell and CMake equivalents.

## On an installation without the grammars

The docs describe this as: "the front ends register nothing, and the miss report names those file types as not indexed." The code I read does not behave that way.

- **`.sh` and `.cmake` routing.** `_ts_language_for` goes through `_grammar_available`, which checks `substrate.has_language`. With no grammar, it returns None, so there is no tree, no harvest, and no `memberdef` rows. This part matches the docs. Nothing crashes.
- **`path` registration is not gated.** `register_synth_paths` runs unconditionally from `clew/cli.py:1909`, and `claims()` tests only the file name and extension. `has_language` is called only from `harvest.py:225`. So `.sh`, `.cmake`, `.yaml` and `.json` files still get `path` rows on the published wheel, and they remain in the file set.
- **The miss report may not fire.** `_not_indexed_scope` in `clew/cli.py` decides "not indexed" by checking whether a scanned file has a `path` row. Shell and CMake files do have one, so they would not be reported as missing. A shell function lookup would then return empty with no explanation. I did not run this, so treat it as a strong reading of the code, not a verified result.
- **YAML and JSON** behave the same on either wheel, because they never had symbols.

## Suggested checks

1. Run `tests/test_script_front_end.py` and `tests/test_not_indexed_report.py` with the published wheel installed, to see whether the miss report names `.sh` files.
2. If it does not, either gate the `claims()` registration on `has_language` for the script types, or change the `substrate.py` docstring. Right now the code and the documentation disagree.
3. `register_paths`'s own docstring still says "JS/TS files", which is stale. It now claims shell, CMake, YAML and JSON as well.