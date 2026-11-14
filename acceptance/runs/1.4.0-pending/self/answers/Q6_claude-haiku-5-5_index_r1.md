**Short answer:** for shell, CMake, YAML and JSON, the index holds a `path` row per file and, for shell and CMake only, function and macro definitions when the grammar is compiled in. It holds no symbols for YAML or JSON, and no call edges for any of them. On an install without the grammars, shell and CMake files stay findable by name but carry no symbols. The docs disagree on one detail there (see below).

**Note on this repo:** the clew repository itself has no `.sh`, `CMakeLists.txt` or `.cmake` files (Glob found none). Its indexed YAML and JSON files are `requirements.yaml`, `.clew.yaml`, the `questions.yaml` targets, `hooks/hooks.json`, and some `.grade.json` and schema files. So I answered from the code, not from a self-automating shell/CMake repo.

**What the index holds, by type**

| File type | Row written | Symbols | Call edges | Where it comes from |
|---|---|---|---|---|
| `.sh`, `.bash`, `CMakeLists.txt`, `.cmake` | `path` row, always | `memberdef` rows for functions, and macros in CMake, when the grammar is present | Not from this layer | `clew/synth.py` (`SCRIPT_EXTS`, `SCRIPT_NAMES`, `_ScriptSymbolHarvester`), `clew/shast.py`, `clew/cmakeast.py` |
| `.yaml`, `.yml`, `.json` | `path` row only | None, by design | None | `DATA_EXTS` in `clew/synth.py` |
| `requirements.yaml` | Read by its own loader | Requirement rows, not symbols | `@req` edges | `ingest_requirements_yaml` in `clew/requirements.py` |
| `.clew.yaml` | Read as config | None | None | `clew/guardconfig.py`, declaration loaders |

The YAML/JSON rule is deliberate. Their grammars expose `block_mapping_pair` and `pair`, and treating those as symbols would put every `steps:` key of every workflow file into the namespace that answers `dossier("my_function")`. So YAML and JSON are "registered and never harvested": they are findable by name and counted in the not-indexed report, and they contribute nothing to function queries.

Shell and CMake are the only two types with a function concept, and their definitions get docs from the `#` block above them (`clew/scriptast.py`). Their grammars are gated by `_OPTIONAL_KEYS = {"bash", "cmake"}` in `clew/harvest.py`.

**What it does not hold**

- No symbols for YAML or JSON, ever.
- No call edges or lock/thread data for any script file. Those layers read only C, C++, Rust, Python, JS/TS and their own walks.
- No script bodies. Search with `corpus='code'` only finds text inside function bodies it parsed.
- Shell and CMake files that are not `.sh` or `.bash` or `.cmake`, or are not named `CMakeLists.txt`, are not indexed at all. The not-indexed report names them.

**On an installation whose parser lacks the grammars**

- The gate is `substrate.has_language`, which asks what is compiled in, not which version is installed. The published `lang-parsing-substrate` 0.11.2 has none of bash, cmake, yaml, json or markdown. The fork that adds them reports the same version string (`clew/substrate.py`).
- For bash and CMake, `harvest._ts_language_for` checks `_grammar_available` and returns no grammar instead of raising. The file gets no definitions and no harvest.
- A `.sh` or `CMakeLists.txt` file still gets a `path` row, because `register_paths` uses `claims()`, and `claims()` never consults the substrate. So the file stays findable by name. `tests/test_script_front_end.py` pins that behaviour.
- The not-indexed report, stamped at build time, names those file types with a count and is served on an empty answer. So "not found" becomes "this file type was not read by this build", which is the distinction the report exists to draw.
- Nothing crashes. A missing or unimportable substrate yields no languages and logs it.

**Discrepancy to know about:** the docstring in `clew/substrate.py` says that on the published wheel "the front ends register nothing" and the miss report names the types. The docstring in `clew/synth.py` and the test say the `path` row is still written and the file is searchable, which is what the code does. The code matches the `synth.py` and test version. The `substrate.py` wording looks stale.

I did not run a build to confirm the degraded path end to end. The conclusions come from the dossiers and the source bodies I read.