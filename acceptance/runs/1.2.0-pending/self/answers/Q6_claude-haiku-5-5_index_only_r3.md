**Short answer:** for YAML and JSON the index holds only that the files exist. For shell and CMake it holds definitions, but only if the installed substrate has the grammars. On an install without them, every one of these files is registered and findable by name, and the index reports that they were not read. It does not fabricate symbols.

**What the index holds, by file type** (from `clew/synth.py`, `tests/test_script_front_end.py`, and the `docs/languages/SCRIPT_INTEGRATION.md` snippets)

| File type | Index holds | Index does not hold |
|---|---|---|
| `.sh`, `.bash` | A `path` row, plus `memberdef` rows for shell functions, with docs taken from the `#` block above each one | Anything from a grammar that isn't compiled in (see below) |
| `CMakeLists.txt`, `.cmake` | A `path` row, plus `memberdef` rows for `function` and `macro`. A macro is recorded as a macro, because it pastes its body into the caller's scope | Same caveat as shell |
| `.yaml`, `.yml`, `.json` | A `path` row only. The file is in the file set and findable by name | Any symbols. Keys like `steps:` are not written as `memberdef` rows, because that would flood the namespace that answers `dossier("my_function")` |

Shell and CMake definitions are written in the same table shapes doxygen uses for Python, so the query layer reads them without changes. Rows are stamped `dg_source='parse'`, so they can be told apart from `ast`-recovered rows.

**What happens on an install whose parser lacks the grammars**

- The published `lang-parsing-substrate` wheel (0.11.2) does not carry the five configuration grammars: bash, cmake, yaml, json and markdown. They come from a fork that is not yet released. `clew/substrate.py` therefore asks what is compiled in, not what version is installed. A version check would not work, because the fork reports the same version string.
- Against that wheel, the router resolves the file to no grammar. The file is still registered and searchable, but it has no symbols. This is a deliberate fallback: the alternative is `ValueError: unknown language key` in the middle of a build.
- The shell and CMake files also get no symbols on that wheel, not only YAML and JSON. The test file says so directly: with the published wheel, "the files carry no symbols, and a query about a deploy script comes back empty."
- An unimportable substrate is treated as "no languages, logged" rather than a crash. The reason given is that the pre-commit gate also consults this check.
- The miss report is measured at build time. It records how many in-scope files of each unread type exist, for example "14 `.sh` files were in scope and none of them are in this index." A query that comes back empty can then be told apart from a symbol that does not exist. An index built before this release reports nothing about this, instead of a fabricated empty set.

**Caveats**

- I did not verify whether call sites inside shell or CMake files produce call edges. The docs say that files with no `path` row get no call edges, and shell and CMake do get `path` rows. I did not confirm the edge behaviour, so treat it as unknown.
- The `docs/languages/SCRIPT_INTEGRATION.md` dossier returned no body text. The table above comes from search snippets and the `clew/synth.py` module documentation.
- `test_ingest_requirements_yaml_reads_the_mapping_keyed_shape` shows YAML requirement catalogs are read on a separate path (the requirements ingest in the docs build), not by the script front end. I did not trace that path.