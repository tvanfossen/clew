**Short answer:** For shell and CMake, clew's index holds function-level rows: names, a doc block, and for CMake the parameters and whether it is a function or macro. For YAML and JSON it holds only a `path` row, so the files are in the file set but have no symbols. On an installation whose substrate lacks the bash or cmake grammar, the shell and CMake files degrade silently, and the report that should explain it does not. I read this from the code and tests; I did not build an index or run the tests here.

**What each file type gets**

| File | Index holds | Index does not hold |
|---|---|---|
| `*.sh`, `*.bash` | `memberdef` rows for `name() {…}` and `function name {…}`. Doc comes from the `#` block directly above. `args` is empty by design (`clew/shast.py`). | Command invocations are not described here; call-layer behaviour not verified. |
| `*.cmake`, `CMakeLists.txt` (by whole name, so `oldCMakeLists.txt` is excluded) | `memberdef` rows for `function` and `macro`, with the parameters and a `kind` that distinguishes the two (`clew/cmakeast.py`). | `set()`/`target_link_libraries` and other commands are not rows. Plain `.txt` is not routed. |
| `*.yaml`, `*.yml`, `*.json` | A `path` row only (`clew/synth.py` `DATA_EXTS`). They are "registered, never harvested." | Keys, values, workflow steps, targets: none of it. A YAML/JSON file yields no symbols and is not in `repo_source_files`. |

**Installation without the grammars**

- **bash and cmake** are gated as optional keys (`clew/harvest.py` `_OPTIONAL_KEYS`). Without them, `_ts_language_for` returns None, so no tree is parsed and no `memberdef` rows are written. The `path` rows are still inserted, because `register_paths` claims files by extension and never checks availability.
- **yaml and json** make no difference, because no grammar is consulted for them at all.
- **Config reading is independent of the substrate.** `.clew.yaml` and `requirements.yaml` go through PyYAML (`pyyaml>=6.0,<8` in `pyproject.toml`), and JSON uses the stdlib.

**Discrepancies to fix**

1. `clew/substrate.py`'s docstring says a missing grammar makes "the miss report name those file types as not indexed." That does not happen. `propose/notindexed.py` builds its candidates from definitions, so a shell or CMake file with no definitions, and every YAML/JSON file, never appears in the report. The same applies to the `synth.py` claim that data files are "named by the not-indexed report."
2. `substrate.missing_languages()` has no production caller, only tests. Nothing logs which grammars are absent, so a build on the published wheel gives no warning at all.
3. The `register_paths` / `_ts_language_for` split means a shell file on a grammar-less install is in the file set with no tree behind it. Its absence is the failure the project says it guards against: a gate that reports success while checking nothing.

Suggested fix: have `register_paths` skip or log claimed files whose grammar is absent, and have `missing_languages` called once at build start with an INFO or WARNING line that names the file count.