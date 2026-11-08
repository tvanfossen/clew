**Short answer:** For shell, CMake, YAML and JSON, the index holds the file's existence and, for shell and CMake, its function definitions. It holds nothing else from YAML or JSON. On an installation whose substrate lacks the bash and cmake grammars, clew does not crash. The shell and CMake files stay in the file set with no symbols, and a miss on them is reported as "not indexed."

**What the index holds**

| File type | Rows written | Source of the rows |
|---|---|---|
| `.sh`, `.bash`, `.cmake`, `CMakeLists.txt` | `path` row plus `memberdef` rows for each function (and CMake macros, recorded as macros) | Parsed by `clew/synth.py` using the bash and cmake grammars via `clew/shast.py` and `clew/cmakeast.py`. Docs come from the `#` block above a definition. |
| `.yaml`, `.yml`, `.json` | `path` row only | Registered so the file is findable by name. Never harvested. |

The stated reason for not giving YAML and JSON symbols is that their grammars expose `block_mapping_pair` and `pair`, not functions. Writing those as `memberdef` rows would put every `steps:` key into the namespace that answers `dossier("my_function")`.

**What it does not hold**

- No symbols for YAML or JSON, so no keys, values or structure are queryable.
- No call edges come from the shell or CMake definition harvesters. The harvest stages I could see describe C/C++, Python and Rust AST work, and the shell and CMake harvesters only emit definitions. I did not find a call-edge layer for shell or CMake.
- A file that defines no function (a shell script with only top-level commands, or a `CMakeLists.txt` that only calls commands) gets a path row and no symbols. The index's own docs describe this as intended.
- Shell and CMake files are only read through the parse-built front end. Doxygen reads neither, so there is no doxygen-side view of them.

**What happens without the grammars**

1. The bash and cmake grammars come from a fork of lang-parsing-substrate that, per `clew/substrate.py`, is not yet released upstream. The fork's wheel reports the same version (0.11.2) as the published one, so clew asks what is compiled in rather than checking a version.
2. `_ts_language_for` calls `_grammar_available`, which checks `_OPTIONAL_KEYS = {"bash", "cmake"}`. If the key is missing, the route resolves to no grammar and returns `None`. `parse_tree` would otherwise raise `ValueError: unknown language key`, and that path is never reached.
3. The `path` rows are still written, because `claims()` checks extensions only and not grammar availability. The files remain searchable by name.
4. The not-indexed report, stamped at build time, names those extensions with counts, for example "14 `.sh` files were in scope and none are in this index." An empty answer about a deploy script therefore says "the file type is not indexed in this build," not "the symbol does not exist."
5. If the substrate cannot be imported at all, `compiled_languages()` returns an empty set and logs an ERROR. The design treats that as a degraded build, not a crash, because the gate also runs on the pre-commit path.
6. A build from before this release stamps no report, so it reports nothing rather than claiming an empty set.

**Inconsistencies in the index's own documentation**

- `clew/substrate.py` says that against the published wheel "the front ends register nothing." The code in `claims()` and `register_paths()` does register `path` rows for shell and CMake by extension alone. The `tests/test_script_front_end.py` docstring describes the same case as "registered and searchable," which matches the code.
- `_OPTIONAL_KEYS` lists only bash and cmake. YAML, JSON and markdown are not in it. That is consistent with YAML and JSON never being routed to a grammar, but the substrate docstring's list of five configuration languages suggests the check covers all five.

**Not verified:** I did not dossier the requirements-YAML ingest path (`test_ingest_requirements_yaml_reads_the_mapping_keyed_shape`) or the `--enrich` YAML path, so I cannot say how much YAML content those paths read. Those are separate from the parse-built front end described above.