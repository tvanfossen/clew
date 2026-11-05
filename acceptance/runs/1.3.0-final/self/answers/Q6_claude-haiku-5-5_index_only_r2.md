**Short answer:** for shell, CMake, YAML and JSON the index holds a file-level inventory plus function-level rows for shell and CMake only. YAML and JSON get no symbols by design. Whether shell and CMake get symbols at all depends on the installed substrate. On an install without those grammars, the files stay in the index as bare paths, and the miss report names them so an empty answer isn't read as absence.

**What the index holds**

| File type | Path row (findable, in file set) | Symbol rows | Other content |
|---|---|---|---|
| `.sh`/`.bash` | Yes | `memberdef` rows for `name() {}` and `function name {}`, each with its `#` doc block | `args` is empty, since shell has no parameter list |
| `CMakeLists.txt`, `.cmake` | Yes | `function` and `macro` rows, macros recorded as macros | Name is taken from the first argument |
| `.yaml`/`.yml`/`.json` | Yes | None, by design | See below |

`clew/synth.py` says YAML and JSON are "registered and never harvested". The reason is given in `tests/test_script_front_end.py`: their grammars only offer `block_mapping_pair` and `pair`, so turning them into rows would fill the namespace that answers `dossier("my_function")` with every `steps:` key. The index does contain them as indexed files with `symbol_count: 0`. I saw this for `.clew.yaml`, `requirements.yaml` and `questions.yaml` files.

Some YAML and JSON content is read semantically, outside the grammar layer:

- **Requirements catalog** (`ingest_requirements_yaml`, `clew/requirements.py`): accepts a flat `[{id,...}]` list or a `requirements:` mapping keyed by id. Any other shape, such as a nested `domains:` tree, yields zero rows, and the table is still created.
- **Data-model and shared-key manifests** (`_parse_data_model_yaml`, `_read_patterns_yaml` in `clew/shared_key_edges.py`): parsed with PyYAML directly. The first of these returns `[]` when PyYAML is unavailable, which is a different failure path from a missing grammar.

**What the index does not hold**

- No symbols or call edges for YAML/JSON content.
- For shell and CMake, the harvest records definitions only. I found no edge or include records for them, so I can't say whether a shell script's calls into C or CMake's `add_library` targets are linked.
- Shell `#` doc blocks are attached only when they sit directly above the definition with no blank line between.
- I could not confirm from the index whether the `scripts/` directory's 74 symbols in this repo are shell definitions. That is the likely source, but I did not verify it.

**On an installation whose substrate lacks the grammars**

The published `lang-parsing-substrate` 0.11.2 wheel does not compile in `bash`, `cmake`, `yaml` or `json`. `clew/substrate.py` probes what is compiled in rather than checking the version, because the fork reports the same version string as the published wheel.

1. `_OPTIONAL_KEYS` is `{bash, cmake}`. `_grammar_available` returns False for those, so the route resolves to no grammar. The build does not crash, which the `_grammar_available` docstring describes as a deliberate choice. The router is capability-gated, so a missing grammar yields no parse error.
2. The shell and CMake files are still registered in `path` (via `claims()`), so they stay in the file set with no `memberdef` rows.
3. YAML and JSON are unchanged in this case, since they never had a grammar route.
4. The build stamps `not_indexed` and `not_indexed_count` (`_not_indexed_scope`, `clew/cli.py`). The stamp is a count per extension, e.g. `.sh=14`, and is served when a query comes back empty. This separates three cases: the symbol doesn't exist, its file type isn't indexed by this build, or its file type is outside the declared scope.
5. If `lang_parsing_substrate` can't be read at all, `compiled_languages()` logs an ERROR and returns an empty set. An unimportable substrate is treated as a broken install, not a crash.

The `not_indexed` stamp is measured at build time, so an index built before the release reports nothing rather than a false "empty". On a published-wheel install, a query for a deploy-script function returns empty with that note attached, and the note is the signal to read the file directly.