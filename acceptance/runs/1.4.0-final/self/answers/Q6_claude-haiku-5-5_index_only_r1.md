**Short answer:** for YAML and JSON the index holds only the file's existence and name. For shell and CMake it holds function and macro definitions, but only when the installed parser has those grammars. This index shows no shell or CMake content at all, so it could be either a repo with none or a build without the grammars. The index alone can't tell which.

**YAML and JSON**

- Each file gets a `path` row and nothing else. It is in the file set and findable by name, and its `symbol_count` is 0. This repo has 16 YAML files (`.clew.yaml`, `.pre-commit-config.yaml`, `requirements.yaml`, the `questions.yaml` targets) and 16 JSON files, all with zero symbols.
- Keys are deliberately not harvested. `steps:`-style mapping keys would flood the same namespace that answers `dossier("my_function")`, so the grammars' `block_mapping_pair` and `pair` nodes are never turned into symbols.
- So a question like "what does `.clew.yaml` set" gets no answer from the index. The file has to be read directly.

**Shell**

- `clew/shast.py` harvests function definitions only, in both bash forms (`name() {…}` and `function name {…}`). Each becomes a `memberdef` row, with the brief taken from the `#` block directly above it. `args` is always empty, since shell has no parameter list.
- Shell variables, sourced files and `case` structure are not held. I have not checked whether call edges are derived from shell functions.
- In this index, a search for `.sh` returns no files, and `shast.py` and `test_shast.py` are the only shell-related files. The index cannot show whether this repo has shell scripts that were left out.

**CMake**

- `clew/cmakeast.py` harvests `function` and `macro` definitions. A macro is recorded as a macro.
- Variables, `target_*` calls, `option()` and `add_library` are not held.
- No `CMakeLists.txt` is indexed. Only `clew/cmakeast.py` and its test match the name. The `CMakeLists` search comes back empty, so the index can't say whether the repo has one.

**What happens without the grammars**

- `clew/substrate.py` probes for each language key, not the wheel version. The published `lang-parsing-substrate` 0.11.2 reports the same version as the fork that carries these grammars, so a version check can't tell them apart.
- With the grammars absent, `compiled_languages()` returns an empty set and logs an ERROR. A missing optional grammar makes `_ts_language_for` return None instead of raising. An unimportable substrate also yields no languages, but only as a logged error. That is deliberate, since a missing optional grammar should not break the pre-commit gate.
- The result is the same for every affected type. A `.sh` or CMake file gets a `path` row and no symbols, like YAML and JSON.
- The not-indexed report is meant to name the uncovered file types, so an empty answer doesn't read as "nothing there". It is stamped at build time and served on an empty answer. My dossier query for a made-up name returned a plain negative with no such report. Either every in-scope type was covered, or the report isn't surfaced through `dossier`. The index can't settle which, so I can't confirm the report's behaviour here.

**What would settle it:** check whether the installed substrate has the `bash` and `cmake` keys. If it does, a repo with `.sh` or `CMakeLists.txt` files should have them indexed, so their absence would mean there are none in the tree. If it doesn't, rebuild against the fork and re-query.