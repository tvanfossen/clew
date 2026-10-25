**Short answer:** for shell, CMake, YAML and JSON, the index holds file-set membership, and for shell and CMake also function and macro definitions. It holds nothing else. On an install without the bash or cmake grammars, shell and CMake files still get path rows but no definitions, and nothing reports that. That contradicts the code's own docstring.

**Premise check.** This repo has no tracked `.sh`, `.bash`, `.cmake` or `CMakeLists.txt` files (`git ls-files` returns 0). It has 37 tracked YAML/JSON files. The index holds 32 of them; the other 5 are under `.github/` and `.claude-plugin/`, which the scope excludes. So the live evidence is YAML/JSON only.

**What each file type gets**

| Type | Path row (file set) | Definitions | Grammar needed |
|---|---|---|---|
| `.sh`, `.bash` | yes | `function` memberdefs, with `#` doc blocks | `bash` |
| `.cmake`, `CMakeLists.txt` (by name) | yes | `function` and `macro definition` memberdefs | `cmake` |
| `.yaml`, `.yml`, `.json` | yes | none, by design | none; no tree is ever built |

- The shell and CMake walkers emit `memberdef` rows only for definitions (`clew/synth.py:136-174`, `clew/harvest.py:96-104`). Top-level commands and variables are not rows.
- YAML and JSON are registered so they are "findable by name" and count as in scope. They have no function concept, so they carry no symbols and no call edges (`clew/synth.py:71-80`). The test `test_the_data_files_are_in_the_file_set_with_no_symbols` pins this.
- The index does not hold YAML or JSON content, keys, or bodies. A path row has no span, so `dossier` has nothing to return for them.
- The live database agrees: 32 YAML/JSON path rows, and no symbol rows for them. The only `js*`/`script*` refids are doxygen file rows for clew's own `jsast.py` and `scriptast.py`.
- clew reads its own YAML and JSON (`.clew.yaml`, `requirements.yaml`, data-model manifests) with `yaml` and `json` directly, outside tree-sitter. Those are config inputs, not indexed code.

**On an install without the grammars**

- **Shell and CMake, no bash/cmake grammar.** `_ts_language_for` returns `None` for them, because `bash` and `cmake` are the only keys in `_OPTIONAL_KEYS` (`clew/harvest.py:145`). That is a silent degrade: no exception, and no log line at the routing point. The result is no definitions. This is pinned by `test_a_missing_grammar_routes_to_nothing_instead_of_raising`.
- **The path rows still get written.** `register_paths` filters only by `claims()` (`clew/synth.py:219-244`) and has no grammar check. It is called unconditionally from `clew/cli.py:1909`.
- **The not-indexed report is therefore wrong.** `_not_indexed_scope` (`clew/cli.py:2646-2676`) treats any scanned file with a `path` row as indexed. So shell and CMake files on a grammar-less install appear as indexed while holding zero symbols.
- **The docstring says otherwise.** `clew/substrate.py:11-17` says that without the grammars "the front ends register nothing, and the miss report names those file types as not indexed." The code does neither.
- **`missing_languages()` has no callers outside tests.** `has_language` is consulted only from `_grammar_available`. So the capability gate that is supposed to decide registration is not wired into registration at all.
- **YAML and JSON** are never routed to a grammar, so whether the installed substrate has `yaml` or `json` changes nothing today.
- **A substrate that fails to import entirely** yields an empty language set (`clew/substrate.py:41-50`). Shell and CMake then degrade, but C and Python are not gated, so a broken install fails loudly on those.

I could not confirm which grammars this installation's substrate actually has. The repo has no `.venv`, and the system Python lacks `lang_parsing_substrate`. The YAML/JSON path rows do not distinguish the two cases, because they are written ungated.

**Recommendation.** Make `register_paths` skip the shell and CMake claims when `has_language` is false, so the miss report names them. The alternative is to correct the docstring and the 1.1.0 claim. The first matches the stated intent, and the test `test_every_new_file_type_is_claimed_for_the_file_set` should gain a grammar-absent case that fails first. I have not changed anything; say the word and I'll make the change.