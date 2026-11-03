**Short answer:** for shell, CMake, YAML and JSON, the index holds a little for two of them and only the file's existence for the other two. On an installation whose parser lacks the grammars, the build still succeeds, the shell and CMake files lose their symbols, and empty answers name the file types that were skipped. I answered from the index alone, so I could not read the source to confirm exact behaviour.

**What the index holds**

| File type | Rows written | What you can ask |
|---|---|---|
| Shell (`.sh`, `.bash`) | `memberdef` rows for function definitions, with docs taken from the `#` block above each one (`clew/shast.py`, `harvest_definitions`) | Find a shell function by name, read its brief, get its line span |
| CMake (`CMakeLists.txt`, `.cmake`) | `memberdef` rows for `function` and `macro` definitions (`clew/cmakeast.py`), and macros are recorded as macros | Find a CMake function or macro by name |
| YAML and JSON | A file-set entry only; no symbols | Find the file by name (`clew/synth.py`: "registered and never harvested") |

**What it does not hold**

- **YAML and JSON keys.** This is deliberate. Their grammars expose `block_mapping_pair` and `pair`, and writing those as `memberdef` rows would put every `steps:` key into the same namespace that answers `dossier("my_function")`.
- **CMake build statements.** A CMake file containing only commands (`add_executable`, `target_link_libraries`, and so on) yields no rows at all (`test_a_cmake_file_that_only_calls_commands_defines_nothing`). The index therefore does not record what the repository builds, with which flags or against which dependencies. Those are the things its own `cmakeast.py` doc says doxygen never reads.
- **Calls made from shell or CMake.** The index does not say whether these get call edges. I could not establish it from the index, so treat it as unknown.
- **Generated or templated content.** The index does not record it either.

**An installation whose parser lacks the grammars**

The concrete case is the published `lang-parsing-substrate` wheel, which is 0.11.2. The fork that adds these grammars also reports 0.11.2, so a version check cannot tell them apart and a pin cannot hold the fork in place. Every front end therefore asks which languages are compiled in (`clew/substrate.py`: `compiled_languages`, `has_language`, `missing_languages`).

What follows from that:

1. **No crash.** A `.sh` file routed to a grammar that is not compiled in would raise `ValueError: unknown language key` mid-parse. The gate prevents that by resolving the route to no grammar.
2. **No symbols for those files.** Shell and CMake definitions are absent. YAML and JSON were already symbol-free.
3. **The gap is named.** The not-indexed report (`tests/test_not_indexed_report.py`) stamps at build time which in-scope file types have no rows. A miss then reads, for example, "14 `.sh` files were in scope and none of them are in this index." Callers can tell "this symbol does not exist" from "this file type was not read" and go read the file directly.
4. **An unimportable substrate is not fatal.** It yields no languages and logs the fact. The substrate doc says this is deliberate: the pre-commit gate also runs through this path, and failing the build over an optional grammar would be the worse outcome.
5. **Old indexes say nothing.** An index built before this release reports no gap at all rather than an empty list, so absence of the report does not mean the tree was fully read.

**One inconsistency in the index.** `tests/test_script_front_end.py` says that on the published wheel a `.sh` file is still registered and searchable, with no symbols. `clew/substrate.py` says that on the published wheel "the front ends register nothing". These disagree about whether the file gets a path entry. I could not settle which is current from the index. The test file is the more specific claim, but check the code before relying on either.