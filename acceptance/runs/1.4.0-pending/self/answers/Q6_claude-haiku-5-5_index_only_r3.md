**Short answer:** For shell and CMake the index holds function and macro definitions, with their `#` doc blocks. For YAML and JSON it holds only the file's existence and name. Neither kind gets call edges, variables, or targets. If the installed parser lacks the grammars, nothing crashes: shell and CMake files silently lose their symbols, and the miss report names them. YAML and JSON are unaffected, because they never needed a grammar to be registered.

**What the index holds, by file type**

| File type | Held | Not held |
|---|---|---|
| `.sh` / `.bash` | `memberdef` rows for both `name() {}` and `function name {}`, with line spans and the `#` block above as the brief. Args are always empty, since shell passes arguments as `$1`/`$@`. | Variables, `source` or sourcing edges, command invocations, and call edges from script bodies. The harvest stages that build call edges walk C/C++ ASTs only. |
| `CMakeLists.txt` / `.cmake` | `function` and `macro` definitions as `memberdef` rows, with parameters taken from the argument list. `kind` records whether it is a function or a macro, since a macro leaks variables into the caller's scope. | `add_executable`/`add_library` targets, `target_link_libraries` dependencies, options, and `set()` variables. These are the things the docs say a reader wants from `CMakeLists.txt`, and they are absent. |
| `.yaml` / `.yml` / `.json` | A `path` row: present in the file set, findable by name, and named by the miss report when a query finds nothing. | Any symbol. Their grammars offer only `block_mapping_pair` and `pair`, and writing those as memberdefs would flood the function namespace with every `steps:` key. Keys, values and structure are not indexed by this layer. |

Two things in the YAML picture are separate from this front end. The index has dedicated Python loaders for specific YAML shapes, such as `requirements.yaml` (the `test_ingest_requirements_yaml…` test) and the enrichment YAML. I did not read those paths, so I can't say what they hold. Also, in the current status the 15 barren files include `requirements.yaml` and several `questions.yaml`, which fits "registered, no symbols."

**What happens when the grammars are missing**

The index does not assume a version. `clew/substrate.py` asks what is compiled in, through `compiled_languages()` and `has_language()`. The fork's five keys are `bash`, `cmake`, `yaml`, `json` and `markdown`. The fork reports the same version string as the published wheel, so a version check cannot distinguish them.

1. **Routing:** `_grammar_available()` in `clew/harvest.py` checks only the optional keys, `bash` and `cmake`. If one is absent, the route resolves to nothing rather than raising. The test `test_a_missing_grammar_routes_to_nothing_instead_of_raising` covers this.
2. **Shell and CMake:** the files are still in the file set, but get no `memberdef` rows. No symbols, no briefs, and no definition lookups for them.
3. **YAML and JSON:** no change, because they are not routed through a grammar.
4. **Reporting:** the build measures, at build time, which in-scope file types have no rows and stamps that report. A query that comes back empty then says something like "14 `.sh` files were in scope and none are in this index," so an empty answer is not read as absence. The report is measured at build time, so an index built before this release reports nothing rather than an empty set.
5. **Unimportable substrate:** `compiled_languages()` returns an empty set and logs at ERROR, not DEBUG. Every front end then registers nothing and the miss report explains why. The docs call an unimportable substrate a broken install, and the gate is kept on the pre-commit path, so a missing optional grammar does not take the build down.

**What this index shows about itself**

The status payload's `not_indexed` list is `(no extension)=3, .csv=3, .rs=2, .toml=2, .jsonl=1, .lock=1, .motor=1, .sql=1`. It names no `.sh`, `.yaml`, `.json` or CMake files, which suggests this build has the fork compiled in. That is an inference from the absence of a report row, not a direct check of the wheel, and the status alone cannot prove the repo has none of those files.