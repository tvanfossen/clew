**Short answer:** For this repository's shell, CMake, YAML and JSON files, the index holds their existence and, for shell and CMake, their function definitions. It does not hold YAML or JSON content as symbols, and it holds no variables, keys, or config values from any of them. On an install whose substrate lacks the grammars, those files drop out of the index and the miss report names them, but the answer is built from the design docs and tests, not from running that install.

**What the index holds**

| File type | Rows | Detail |
|---|---|---|
| `.sh`, `.bash` | `memberdef` rows for `name() {…}` and `function name {…}` | Doc comes from the `#` block directly above. `args` is always empty because shell has no parameter list. Classes are empty. |
| `CMakeLists.txt`, `.cmake` | `memberdef` rows for `function()` and `macro()` | Macros are recorded as macros. |
| `.yaml`, `.yml`, `.json` | A `path` row per file, zero symbols | Findable by name, but no `memberdef`, so no keys (`steps:`, etc.) enter the symbol namespace. |

I confirmed this from the index's own data. `.clew.yaml`, `requirements.yaml`, `.pre-commit-config.yaml`, and the `acceptance/targets/*/questions.yaml` files are all indexed with `symbol_count: 0`. The `.sh` and `.cmake` harvesters (`clew/shast.py`, `clew/cmakeast.py`) are wired through `clew/synth.py`.

**What it does not hold**

- Any YAML or JSON key, value, or structure as a queryable symbol. This is deliberate: the design doc says keys would drown real functions.
- Shell variables, `source` relationships, or CMake `set()`/`option()`/targets. The harvesters only record function and macro definitions. I found no harvester for those.
- Call edges from shell or CMake. The index does not say whether those edges exist for these languages, so I can't confirm either way.
- `.jsonl`, `.toml`, `.csv`, `.sql`, and extensionless files. The current build's not-indexed report lists these, and `.jsonl` is not `.json`.

**What happens on an installation without the grammars**

The gate is `clew/substrate.py`. It asks what is compiled into the installed `lang-parsing-substrate` wheel, not what version is installed. The upstream fork that carries these grammars reports the same version string as the published wheel, so a version check can't tell them apart.

- The front ends register nothing for missing languages. Routing to an absent grammar returns "no grammar" instead of raising `ValueError`.
- Files in those types are not in the file set, so they get no rows.
- An empty answer for a name in those files is then reported as "this file type was not indexed here", which points the caller to read the file directly. This comes from `clew/cli.py` and `clew/query/models.py`, which stamp the not-indexed counts at build time.
- The substrate gate has no crash path: an unimportable substrate yields no languages and logs an error.

Two caveats. First, `_OPTIONAL_KEYS` in `clew/harvest.py` lists only `bash` and `cmake`, so the per-route check covers shell and CMake. The docs say YAML and JSON are also absent on the published wheel, but I could not confirm from the index which check gates their registration. Second, the docs disagree slightly on YAML/JSON: `synth.py` says they are "registered and never harvested," while `substrate.py` says the front ends "register nothing." The tests I could read support the second reading for the absent-grammar case.