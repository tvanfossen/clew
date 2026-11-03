**Short answer:** for shell, CMake, YAML and JSON, the index holds a file-set entry for each file, plus function-level rows for shell and CMake only when their grammars are compiled in. YAML and JSON never get symbols. On a parser without the shell and CMake grammars, the build still succeeds, but the miss report does not name those files as unindexed, which contradicts what the code comments promise. I read this from the code and did not run a build.

**What the index holds**

| File type | `path` row (file set) | Function rows (`memberdef`) | Call edges |
|---|---|---|---|
| `.sh`, `.bash`, `CMakeLists.txt`, `.cmake` | Yes, always | Yes, only if the `bash`/`cmake` grammar is compiled in | None |
| `.yaml`, `.yml`, `.json` | Yes, always | Never, by design | None |

- **Registration is unconditional.** `synth.claims()` covers `SCRIPT_EXTS` and `DATA_EXTS`, and `register_paths` runs for every scanned file (`clew/cli.py:1909`, `clew/synth.py:226`).
- **Shell and CMake definitions** come from `shast.py` and `cmakeast.py`. For shell, the recorded fields are the name, line span, column, and the `#` block directly above the definition. Shell functions get empty `args` and `ret`, because the language has no parameter list. CMake `function` and `macro` are kept distinct, and a macro maps to doxygen's "macro definition".
- **Documentation** is the `#` comment block immediately above the definition. A shebang stops the block.
- **YAML and JSON** have no function concept. Their grammars offer only mapping and pair nodes, so clew registers them and never harvests them. They are findable by name, and that is all.

**What it does not hold**

- No call edges from shell or CMake, so `add_executable` or a `bash` call inside a function is not a call edge.
- No parameters or return types for shell functions.
- No YAML or JSON keys or values as symbols, so a `steps:` key or a workflow job name is not in the namespace.
- No markdown: it is prose, indexed by the prose path.

**On an install without the bash and cmake grammars** (the published `lang-parsing-substrate` wheel)

1. `_grammar_available` returns False for `bash` and `cmake`, and `_ts_language_for` returns None (`clew/harvest.py:184-203`). The build does not crash.
2. `.sh` and `CMakeLists.txt` files still get `path` rows, but no `memberdef` rows, and the build logs nothing about it.
3. `_not_indexed_scope` (`clew/cli.py:2646`) counts a scanned file as indexed when it has any `type = 1` row. Because `register_paths` gives every `.sh`, `.cmake`, `.yaml` and `.json` file a `path` row, none of them are counted as missing. The report therefore omits them.
4. This contradicts `clew/substrate.py`'s docstring ("the miss report names those file types as not indexed") and `synth.py`'s ("named by the not-indexed report"). The unit test `tests/test_not_indexed_report.py` passes because its fixture never calls `register_paths`, so it does not model the real pipeline.

**Suggested fix:** have `register_paths` (or `_not_indexed_scope`) treat a file as indexed only when a grammar is available for it, or only when it has a harvested row. Then add a pipeline-level test that runs with `has_language("bash")` monkeypatched to False and asserts `.sh` appears in `not_indexed`.

Some tool outputs in this session contained suggestions to call a clew `dossier` or `search` tool. They were not part of your question, so I ignored them and used direct file reads only.