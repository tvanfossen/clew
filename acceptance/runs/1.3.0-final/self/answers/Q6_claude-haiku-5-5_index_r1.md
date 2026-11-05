**Short answer:** for shell, CMake, YAML and JSON the index holds a file-level row, and for shell and CMake also the function and macro definitions. It holds nothing about YAML or JSON contents. On an install without the grammars, the shell and CMake definitions are missing, and the not-indexed report is the only place that absence shows up.

**What the index holds**

| File type | `path` row (file set) | Definitions (`memberdef`) | Content searchable |
|---|---|---|---|
| `.sh`, `.bash` | yes | yes: `name() {…}` and `function name {…}` only | via the `#` doc block above each definition |
| `CMakeLists.txt`, `.cmake` | yes | yes: `function` and `macro` (recorded as different kinds) | via the same kind of doc block |
| `.yaml`, `.yml`, `.json` | yes | no, by design | no |

- **Registration.** `claims()` in `clew/synth.py:191` is what puts a file into the file set. It is not gated on grammar availability, so a `.yaml` or `.sh` file gets its `path` row on any install. A YAML file is "findable by name" and that is all.
- **Why YAML and JSON get no symbols.** Their grammars only offer `block_mapping_pair` and `pair`. Writing those as `memberdef` rows would put every `steps:` key into the namespace that answers `dossier("my_function")`. The file's own comments in `clew/synth.py` (around lines 69–80) and the `tests/test_script_front_end.py` docs say this explicitly.
- **Shell.** Arguments are empty because shell has no parameter list (`clew/shast.py`). The doc block must sit immediately above the definition; a blank line separates it.
- **CMake.** A `macro` is recorded as a macro, because its body leaks variables into the caller's scope. A `function` gets its own scope. The name comes from the first argument of `function_command`, since the grammar has no `name` field.

**What it does not hold**

- No YAML or JSON keys, values, schema, or requirement IDs as symbols. The `requirements.yaml` and `.clew.yaml` files are in the file set by name only.
- No content from YAML or JSON in any search corpus. `code` covers function bodies, and `prose` covers markdown and reStructuredText only.
- No symbols at all for a shell script that defines no functions, which is common for deploy and CI scripts. The script still gets a `path` row.
- I did not confirm whether shell or CMake files produce call edges. The `clew/synth.py` docs describe the rows written, and the search found nothing about call edges for them. Treat that as unverified.

**On an install whose parser lacks the grammars**

The docs in `clew/substrate.py` say the bash, cmake, yaml and json grammars sit in an unreleased fork of lang-parsing-substrate. The published wheel reports the same version string, so a `pip install -U` or fresh venv can silently drop them. Clew therefore asks what is compiled in, not what version is installed.

1. `has_language(key)` returns False for the missing key (`clew/substrate.py:62`). `compiled_languages()` only logs an error when the import fails. A wheel that is present but lacks the keys is silent apart from the report.
2. `_ts_language_for` (`clew/harvest.py:184`) returns None for `.sh` and `CMakeLists.txt` when `bash` or `cmake` is absent. The test `test_a_missing_grammar_routes_to_nothing_instead_of_raising` pins this. It deliberately does not gate C, C++, Python or Rust, since a wheel missing those is a broken install and should fail loudly.
3. The shell and CMake files remain in the file set with no definitions. YAML and JSON are unchanged, because they were never harvested.
4. `clew/query/corpus.py` (`_not_indexed`, around line 326) reads a report stamped at build time by `_not_indexed_scope` in `clew/cli.py`. It names the in-scope file types that produced no rows, so a `dossier` miss on a deploy script reads as "this build did not read `.sh`" rather than "the function does not exist". The report is measured at build time, not query time, so an index built before this release claims nothing rather than reporting a false empty set.

Caveat: `clew/harvest.py` anchors `test_a_missing_grammar_routes_to_nothing_instead_of_raising` as mismatched, so the file changed since the index was built. I read the test from the current file, but I did not run the suite, so the degrade behaviour above is taken from the code and test source, not from a test run.