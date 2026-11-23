## Short answer

For shell and CMake, the index holds one row per function or macro, with the `#` comment block above it as documentation. For YAML and JSON it holds only a file-set entry: the file can be named, but nothing inside it is indexed. On an installation without the bash and cmake grammars, shell and CMake fall back to file-set entries with no symbols and nothing raises. My reading of the code says the not-indexed report then fails to name those files, which contradicts the docs. I did not execute that path, because this acceptance copy has no `.venv`.

## What the index holds

| File type | Row written | Source |
|---|---|---|
| `.sh` `.bash` | `path` row, plus `memberdef` per `name() {}` or `function name {}` | `clew/shast.py`, `clew/synth.py` |
| `CMakeLists.txt` `.cmake` | `path` row, plus `memberdef` per `function()` (kind `function`) and `macro()` (kind `macro definition`) | `clew/cmakeast.py` |
| `.yaml` `.yml` `.json` | `path` row only | `clew/synth.py:80`, `register_paths` |

- **Documentation:** the `#` block directly above a definition, with no blank line between. A shebang is not documentation.
- **Arguments:** shell functions have empty `argsstring`, because the language has no parameter list. CMake functions report named parameters.
- **Provenance:** rows are stamped `dg_source='parse'`.
- **YAML and JSON:** `dossier('requirements.yaml')` returns the file with `symbol_count: 0`. Keys are not symbols, by design (`clew/synth.py:71-80`).

## What it does not hold

- **YAML and JSON content.** Their keys and values are not indexed. `search(corpus='code')` covers function bodies and `corpus='prose'` covers markdown and rst, so YAML text is searchable nowhere.
- **Shell or CMake statements outside definitions.** Top-level commands, variables and `add_executable` targets get no rows.
- **Call edges from shell or CMake.** `shast.py` and `cmakeast.py` only harvest definitions; a grep for call-site extraction in `shast.py` found nothing.
- **Dot-directories.** `.github/workflows/ci.yml` is pruned from scope and `dossier` reports it as not indexed (`docs/languages/SCRIPT_INTEGRATION.md`, the scope note).

## Installation without the grammars

The gate is in `clew/harvest.py:137` (`_OPTIONAL_KEYS = {"bash", "cmake"}`) and `clew/substrate.py`. Shell and CMake are the only gated grammars, and it is a capability check against the installed wheel, not a version check. Without them:

1. `_ts_language_for` returns `None` for `.sh` and `CMakeLists.txt`, so no tree is parsed and no `memberdef` rows are written. `tests/test_script_front_end.py:128` pins this, with no exception.
2. YAML and JSON are unaffected. Registration needs no grammar, so they get the same `path` row on either install.
3. The stamping step is where the design seems to break. `register_paths` claims `.sh` and `CMakeLists.txt` by extension and name with no grammar check, and `cli.py:1909` calls it unconditionally. `_not_indexed_scope` (`cli.py:2646-2684`) counts a scanned file as missing only if it has no `type = 1` `path` row. So on a no-grammar install, shell and CMake files have path rows and are never counted as missing. The report stays silent about them.
4. The test that looks like it covers this, `tests/test_not_indexed_report.py`, builds its `path` rows by hand and never runs `register_paths`. Nothing exercises the real pipeline.
5. The result is that `dossier` on a `.sh` file returns the same shape as a shell file with no functions: `found`, `harvested`, zero symbols. That is the absence-versus-emptiness problem `AGENTS.md` warns about.

## Suggested fix

Write a RED test that builds an index with `compiled_languages` patched to exclude `bash` and `cmake`, then asserts the `.sh` and `CMakeLists.txt` files appear in `not_indexed`. The likely fix is to have `register_paths` skip shell and CMake when their grammars are absent, or to have `_not_indexed_scope` count claimed-but-unparsed files. I have not made the change; say the word and I will.