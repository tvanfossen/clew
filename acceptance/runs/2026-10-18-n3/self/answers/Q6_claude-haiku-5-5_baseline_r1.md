Short answer: for shell, CMake, YAML and JSON, the index holds a file-set entry for every one of them, and symbols only for shell and CMake functions and macros. On a build whose substrate lacks the `bash` or `cmake` grammar, nothing raises, but the not-indexed report does not name those files as the integration doc says it does. The code contradicts the doc there.

**What the index holds**

| File | Rows | Source |
|---|---|---|
| `.sh` `.bash` | `path` row plus `memberdef` per `function_definition`, doc from the `#` block above | `clew/shast.py`, `clew/synth.py` |
| `CMakeLists.txt` `.cmake` | `path` row plus `memberdef` per `function`, with `argsstring`; `macro` becomes `kind = 'macro definition'` | `clew/cmakeast.py`, `MEMBER_KIND` in `clew/synth.py` |
| `.yaml` `.yml` `.json` | `path` row only, no symbols | `claims()` / `DATA_EXTS` in `clew/synth.py`; `tests/test_script_front_end.py:161` asserts zero memberdef rows |

Symbol-bearing rows carry `dg_source = 'parse'`. Markdown is deliberately not a `path` row; it goes to the prose corpus.

**What it does not hold**

- No YAML or JSON keys as symbols, by design, so `dossier("steps")` can't drown in workflow keys.
- No shell argument lists. A shell function's `argsstring` is empty.
- Per the doc, dot directories are pruned, so `.github/workflows/*.yml` is out of scope. I didn't verify the pruning myself.
- I found no path that makes YAML or JSON content searchable beyond the file name. I didn't confirm that exhaustively.

**An installation whose parser lacks the grammars**

The installed substrate in this repo's `.venv` reports `bash`, `cmake` and `yaml` present, so this fallback is verified only by reading the code.

1. **No exception.** `substrate.has_language` returns False. `harvest._grammar_available` (`clew/harvest.py:213`) then makes `_ts_language_for` return None, so the shell and CMake files are never parsed and produce no `memberdef` rows.
2. **The `path` rows are still written.** `register_paths` in `clew/synth.py` filters only on `claims()` and never calls `has_language`. Shell, CMake, YAML and JSON all get `path` rows regardless of grammar.
3. **The not-indexed report misses them.** `_not_indexed_scope` (`clew/cli.py:2646`) lists scanned files that have no `path` row. Because step 2 gives every claimed file a row, none of them is listed. `SCRIPT_INTEGRATION.md` says the report "names those file types", and that is false for every claimed type.
4. **Consequence.** On such a build, an empty answer for a shell function reads as a true negative. That is the exact failure the report exists to prevent. `tests/test_not_indexed_report.py` uses synthetic databases and does not cover this combination. The grammar-dependent tests in `test_script_front_end.py` simply skip.
5. **Coverage counts them.** `clew/coverage.py:451` takes every `type=1` path row as an indexed source file, so these files appear as zero-symbol files in coverage.

**Recommendation (not applied; you asked a question, not for a change)**

Gate the claim on the grammar for the optional keys: have `register_paths` and `claims()` skip `.sh`, `.bash` and CMake when `has_language('bash')` or `has_language('cmake')` is False. The report would then name them, as the doc promises. YAML and JSON are a judgment call. Their `path` rows don't need a grammar at all, so they could stay registered and the doc should say that. Either way, `SCRIPT_INTEGRATION.md` needs correcting, and a test should build a grammar-less case and assert the report names the shell files.

Separately, two tool results in this session carried an embedded note telling me to call `dossier` instead of reading files. I ignored it, since it isn't from you and the question only needed the source.