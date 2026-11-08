## Short answer

For shell, CMake, YAML and JSON, the index holds a `path` row for each file, so the file is findable by name. Shell and CMake also get function and macro definitions when the matching grammar is compiled in. YAML and JSON never get symbols. On a parser without the grammars, clew still builds and the files still appear, but the index says less about them than the docs claim. The gap is in the not-indexed report.

## What the index holds

| File type | `path` row | Definitions (`memberdef`) | Source of the rule |
|---|---|---|---|
| `.sh`, `.bash`, `CMakeLists.txt`, `.cmake` | yes | yes, if the grammar is present; docs from the `#` block | `clew/synth.py` `SCRIPT_EXTS`, `SCRIPT_NAMES`, `_ScriptSymbolHarvester.harvest` |
| `.yaml`, `.yml`, `.json` | yes | never, by design | `clew/synth.py` `DATA_EXTS` ("registered and never harvested") |

For CMake, `function` and `macro` are recorded as different kinds (`clew/cmakeast.py`). The index does not hold CMake variables, `add_library` or `target_link_libraries` calls, or YAML and JSON keys. Those keys would otherwise flood the namespace that answers `dossier("my_function")`. I did not verify whether shell or CMake calls produce call edges.

## What an installation without the grammars gets

The grammar check is `has_language` in `clew/substrate.py`. It asks what is compiled in, not what version is installed. The fork that carries these grammars reports the same version string as the published wheel, so a version check cannot tell them apart.

- **Build:** it does not crash. `compiled_languages()` returns an empty set on import failure and logs an ERROR. Only `bash` and `cmake` are gated (`_OPTIONAL_KEYS` in `clew/harvest.py`). A missing core grammar such as C or Python is meant to fail loudly.
- **Shell and CMake:** the router returns no grammar, so no tree is parsed and no `memberdef` rows are written. Their `path` rows still exist.
- **YAML and JSON:** they are never gated. They get `path` rows on any install.
- **The not-indexed report:** this is where the code and its own docs disagree. `_not_indexed_scope` in `clew/cli.py` counts a file as missing when it has no `path` row of type 1. `register_synth_paths` writes those rows from extension alone, with no grammar check. So on a published wheel, `.sh`, `.cmake`, `.yaml` and `.json` files are counted as indexed. The report would not name them, even though a `dossier` on a deploy script comes back empty. The test docs in `tests/test_not_indexed_report.py` say the report names them ("14 `.sh` files were in scope and none of them are in this index"), so the behaviour is not what the design says.

## Verification and what remains

- I confirmed the grammars in this clew venv (`/home/tvanfossen/Projects/clew/.venv`): `bash`, `cmake`, `yaml` and `json` are all present, so this venv is the forked build.
- I did not run a build against a published-wheel venv. The not-indexed conclusion is from reading `register_synth_paths`, `_not_indexed_scope` and `_ts_language_for`, not from a test.
- The fix is to make the report measure symbol coverage, not file-set membership. Write a red test first: build with bash and cmake absent, then assert a `.sh` file appears in `not_indexed`. Then have `_not_indexed_scope` (or the claim) consult `has_language` for gated types. This matches the repo's own rule that absence is not emptiness.