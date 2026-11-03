**Short answer:** for shell and CMake, the index holds one row per function or macro definition. For YAML and JSON it holds only a file-path row, so those files are findable by name and carry no symbols. Two things in the question don't match this repository, and the degraded-install behaviour is documented inconsistently, so read the last section before relying on it.

**The premise doesn't match this repo.** The tracked tree has zero `.sh`, `.bash`, `.cmake` or `CMakeLists.txt` files. It has 37 data files: 18 JSON, 16 YAML and 3 `.yml`. So the shell/CMake half of the question has nothing to test here. The rest of this answer draws on clew's code and docs, which handle those file types.

**What the index holds**

The parse-built front end is `clew/synth.py`. It writes doxygen-shaped `path`, `memberdef` and `compounddef` rows, so later stages run unchanged. Routing is by extension, and `CMakeLists.txt` is matched by name:

| File type | Rows written | Source of rows |
|---|---|---|
| `.sh`, `.bash`, `.cmake`, `CMakeLists.txt` | `path` plus a `memberdef` per function or macro, with the docs from the `#` block | `clew/shast.py`, `clew/cmakeast.py` |
| `.yaml`, `.yml`, `.json` | `path` only, no symbols | none, by design |

The YAML/JSON exclusion is deliberate. Their grammars offer `block_mapping_pair` and `pair`, and writing those as symbols would put every `steps:` key into the namespace that answers `dossier("my_function")`. Checking the index confirms it: `requirements.yaml` is found and harvested with zero symbols, and `clew/mcp_server/descriptions/dossier.json` is found too.

**What it does not hold**

- YAML keys and values, and JSON pairs. The one exception is the requirements catalog, which tests say is ingested separately. I did not re-verify that path.
- CMake variables, targets, `option()` and `add_executable`. Only function and macro definitions are recorded.
- Top-level shell statements and variable assignments.
- `.github/workflows/ci.yml` is not in the index. A `dossier` call returned a definitive negative. I did not establish why, and the likely cause is the declared scope, which is unverified.

**The not-indexed report.** At build time, `_not_indexed_scope` in `clew/cli.py` compares the scanned files with the `path` table. It stamps the count exactly and names up to 12 extensions. An empty answer then reads as "not indexed" rather than "absent". Note that it counts only files with no `path` row.

**On an install whose parser lacks the grammars**

- `has_language` and `missing_languages` in `clew/substrate.py` ask what is compiled in, not what version is installed. An unimportable substrate logs an error and yields no languages, rather than crashing.
- The router refuses the route. `_ts_language_for("scripts/deploy.sh")` returns `None` when bash is absent, and the test pins this. C and Python are not gated, so a broken install fails loudly there.
- I confirmed that the project's venv substrate compiles in all the grammars, including bash, cmake, yaml and json. So this environment does not exercise the degraded path.

**The inconsistency.** The docs disagree about what happens to `.sh`, `.yaml` and `.json` files on the published wheel:

- `clew/substrate.py` says the front ends "register nothing" and the miss report names those types as not indexed.
- `tests/test_script_front_end.py` says the file "is registered and searchable, and it carries no symbols."
- The code agrees with the second. `register_paths` and `claims()` decide by extension alone and never call `has_language`. So on the published wheel, shell, YAML and JSON files would still get `path` rows. They would be findable by name, carry no symbols, and not appear in the miss report at all.

I'm reporting this from reading the code. It would settle with one build against the published wheel: check that a `.sh` file has a `path` row, and check whether `not_indexed` names `.sh`.