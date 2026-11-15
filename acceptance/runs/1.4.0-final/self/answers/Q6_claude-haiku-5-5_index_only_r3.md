**Short answer:** for shell and CMake, the index holds definitions and their doc blocks. For YAML and JSON, it holds only the file's existence and name. On an install without the grammars, shell and CMake degrade to the same state as YAML and JSON, and an empty answer does not tell you why.

**What the index holds**

- **Shell (`.sh`, `.bash`):** one `memberdef` row per function, in both bash spellings, `name() { … }` and `function name { … }`. The docs come from the `#` block directly above. Arguments are empty by design, since shell functions take `$1`/`$@`. Shell functions are the only shell symbols; the harvest module (`clew/shast.py`) describes no other shell constructs. (`clew/shast.py`, `tests/test_shast.py`)
- **CMake (`CMakeLists.txt`, `.cmake`):** one row per `function` or `macro`, with `kind` recorded so a macro is not mistaken for a function (macros leak variables into the caller). Parameters are the signature. A file that only calls commands defines nothing. (`clew/cmakeast.py`, `tests/test_cmakeast.py`)
- **YAML and JSON:** a `path` row only. Their grammars offer `block_mapping_pair` and `pair`, and those were deliberately not written as symbols, so `steps:` keys in every workflow file don't flood the namespace behind `dossier("my_function")`. They are findable by name and named by the not-indexed report. (`clew/synth.py`, `tests/test_script_front_end.py`)

**What it does not hold**

- No YAML or JSON keys, values, or structure.
- For CMake, no targets, options, dependencies, or `add_executable`-style commands. "How is this target built" is answered only by the definitions in the file.
- No symbols at all for any YAML or JSON file, so no call edges, no threads, and no requirements from them.
- For shell, the module documents definitions only. I found no indexed call edges from shell scripts, so I would not claim a script-to-script call graph.
- Files that do not reach a grammar are registered but not parsed, so their contents are not searched.

**What happens when the parser lacks the grammars**

This is the part I'd treat as the actual answer. `synth.py` says the router is capability-gated. `parse_tree` raises `ValueError: unknown language key` for a grammar the installed wheel lacks, and the router catches that case. The route resolves to no grammar, so:

1. The `.sh` or `CMakeLists.txt` file is registered and findable by name.
2. It gets no `memberdef` rows, so no symbols and no docs.
3. A query about a deploy script returns empty.
4. The not-indexed report, which is stamped at build time, names the file types that were in scope but held no rows. Without it, an empty answer cannot be told apart from "the symbol does not exist."

The docstring says the published substrate is one such install, which would mean shell and CMake are absent there too, not just YAML and JSON. I could not measure that from the index. It comes from docstrings and tests, so verify it by building on the target install.

Two caveats:
- The not-indexed report is stamped only by builds made with this release. An index built earlier reports nothing, so its empty answers look like plain absence.
- The index's `_ast_parse_one_file` entry is flagged `anchor_mismatch`, so its line numbers may be stale. I used its described behavior, not its exact lines.