**Short answer:** for shell, CMake, YAML and JSON, the index holds the file paths and, for shell and CMake, the function and macro definitions. It holds no symbols for the contents of YAML or JSON files. If the installed parser lacks the grammars, the build degrades without crashing: those files are registered but contribute nothing, and an empty answer names the file types that were not read.

**What the index holds**

| File type | In the file set | Symbols | Source of the rows |
|---|---|---|---|
| `.sh`, `.bash` | yes | yes: `name() { }` and `function name { }` only | `clew/shast.py`, written to `memberdef` by `clew/synth.py` |
| `CMakeLists.txt` (matched by whole name), `.cmake` | yes | yes: `function` and `macro` definitions only | `clew/cmakeast.py` |
| `.yaml`, `.yml`, `.json` | yes | none | registered, never harvested |

Shell and CMake definitions take their doc text from the `#` block directly above them, and a blank line between the block and the definition means no doc. Tags such as `@version` and `@req` are kept as literal text. A shell function has no parameter list, so its `args` are empty, which is a fact about bash rather than a gap in the harvest. CMake records whether each definition is a `function` (own scope, named parameters) or a `macro` (body pastes into the caller's scope).

**What it does not hold**

- Top-level shell or CMake statements: `add_executable`, `target_link_libraries`, the body of a deploy script outside any function. The harvest takes definitions only.
- Any YAML or JSON key. Writing `block_mapping_pair` or `pair` as `memberdef` rows would put every `steps:` key into the namespace that answers `dossier("my_function")`. So those files are findable by name, but `dossier` returns no symbols from them.
- Call edges or dataflow from these files, as far as I can tell from the module docs. I did not confirm that directly.

Some YAML and JSON are still read, but by clew's own code rather than the index. `.clew.yaml` and the shared-key and data-model manifests are parsed by `_read_mapping`, `load_shared_key_patterns` and `_parse_data_model_yaml`. Those results feed the declaration and edge layers, not the symbol table.

**On an installation whose parser lacks the grammars**

- `clew/substrate.py` decides this by asking what is compiled in, not by checking a version. The fork that adds bash, cmake, yaml, json and markdown reports the same version string (0.11.2) as the published wheel, so a version check cannot tell them apart. `compiled_languages()` returns the keys, and `missing_languages()` returns the absent ones in the order asked.
- With the published wheel the new keys are absent. The routing is capability-gated, so a `.sh` file resolves to no grammar. It is registered and searchable, with no symbols, the same outcome as YAML. No `ValueError` reaches the build.
- A substrate that cannot be imported at all yields no languages and logs an ERROR. Per the module docs, this is treated as a broken install rather than a silent gap, and that log line is the only signal.
- The not-indexed report is stamped at build time. It says, for example, that 14 `.sh` files were in scope and none are in the index. That lets a caller tell "the symbol does not exist" from "this build did not read that file type". An index built before this release reports nothing rather than an empty set it did not measure.

**Limits of this answer:** I worked from the index's documentation and symbol records, not the source bodies, and I did not query the stamped not-indexed report on this target. The `cmakeast.py` record shows 8 symbols and the shell harvester has tests, which suggests this particular index was built with the grammars present. I could not confirm that from the index alone.