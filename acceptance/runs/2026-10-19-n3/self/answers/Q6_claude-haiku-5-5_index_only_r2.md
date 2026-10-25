The index holds definitions for shell and CMake, file-level entries for YAML and JSON, and nothing about what the files do. On an installation without the grammars, clew degrades: the files are named in the miss report, nothing raises, and nothing is harvested.

**What the index holds**

| File type | In the index | Source of the claim |
|---|---|---|
| Shell (`.sh`, `.bash`) | Function definitions as symbols, with line spans and the `#` comment block as the brief | `clew/shast.py` `harvest_definitions`; tests in `test_shast.py` |
| CMake (`CMakeLists.txt`, `.cmake`) | `function` and `macro` definitions as symbols, with spans and briefs | `clew/cmakeast.py` `harvest_definitions`; `test_cmakeast.py` |
| YAML (`.yaml`, `.yml`) and JSON (`.json`) | A file-set entry, findable by name, with no symbols | `clew/synth.py` `DATA_EXTS`; `test_the_data_files_are_in_the_file_set_with_no_symbols` |
| Markdown | Not a symbol-bearing file; the repo's prose is a separate full-text corpus | `docs/languages/SCRIPT_INTEGRATION.md` |

The shell and CMake payloads carry only definitions: a `functions` list and an empty `classes` list. A CMake file that only calls commands such as `add_library` defines nothing and yields no rows. Both shell function spellings are harvested.

**What it does not hold**

- No symbols for YAML or JSON at all. Their grammars offer `block_mapping_pair` and `pair`, which clew does not harvest. The repo's own doc says they are "registered and never harvested."
- No command or invocation records for CMake and shell. The payload has no call list, so a CMake target's dependencies or flags are not queryable.
- YAML and JSON content is not searchable as symbols. I could not confirm from the index whether their body text is searchable at all; "findable by name" is the only documented claim.
- Not every YAML file is indexed. The scope note says YAML in `conf/`, `deploy/`, or the repo root is indexed, while CI workflows under dot directories are not. The test suite does claim `.github/workflows/ci.yml` routes to the front end, so the two statements conflict and I could not resolve which governs.

**On an installation whose parser lacks the grammars**

- The parser registry is `lang-parsing-substrate`. The bash and cmake grammars are the only optional keys (`_OPTIONAL_KEYS`). Before routing a file, clew asks `substrate.has_language`. If the answer is no, `_ts_language_for` returns `None` and the file is not harvested.
- The file stays in the file set. A query that finds nothing names the skipped types in the not-indexed report. The test `test_a_missing_grammar_routes_to_nothing_instead_of_raising` pins this.
- If the substrate module is missing entirely, `compiled_languages()` returns an empty set rather than raising (`test_an_unimportable_substrate_degrades_rather_than_raising`).
- C, C++, Python, Rust, JavaScript, and TypeScript are not gated (`_ALWAYS`). A wheel without them is treated as a broken install, and clew fails loudly.
- The gate measures capability rather than comparing versions (`tests/test_substrate_capability.py`). The substrate's language set is recorded in the acceptance identity, and the substrate version is part of the cache key.
- YAML and JSON are registered only in the fork of lang-parsing-substrate, which the repo describes as open upstream and not yet merged. The test file says the five fork languages are present "only while the dev wheel is installed." On a stock installation, I could not confirm from the index whether YAML and JSON still enter the file set. Since they carry no symbols either way, the practical loss is only the by-name entry.

So a stock installation loses shell and CMake definitions and gets a not-indexed message in their place. It does not get an error, a crash, or a partial parse.