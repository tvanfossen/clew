The index holds the four file types at different depths, and it degrades explicitly rather than silently when a grammar is missing. Everything below comes from the index's own documentation and symbol records for this repository; I did not read any source files directly.

**What the index holds, by file type**

| File type | Holds | Does not hold |
|---|---|---|
| Shell (`.sh`, `.bash`) | Function definitions as `memberdef` rows, with docs from the `#` block above each definition | Anything about the file when the bash grammar is absent |
| CMake (`CMakeLists.txt`, `.cmake`) | Function and macro definitions as rows; macros are recorded as macros | Anything about the file when the cmake grammar is absent |
| YAML (`.yaml`, `.yml`) | A `path` row, so the file is in the file set and findable by name | Any symbols. Its grammar offers `block_mapping_pair`, which is not a function concept, so writing those rows would flood the symbol namespace with every `steps:` key |
| JSON (`.json`) | Same as YAML: a `path` row, no symbols | Same as YAML |

For this repository the index reports 16 indexed `.yaml` files, including `.clew.yaml`, `.pre-commit-config.yaml`, `requirements.yaml`, and the `acceptance/targets/*/questions.yaml` files. Each has zero symbols. I did not find any `.sh` files in the index; the not-indexed summary lists no `.sh` files for this scope, so none were in scope to be read.

**How the routing works**

- `clew/synth.py` (`claims`, `script_claims`, `emit_definitions`) is the parse-built front end. It is purely extension- and name-based, so it claims YAML and JSON files regardless of whether a grammar is present.
- `clew/harvest.py` maps shell and CMake to `substrate:bash` and `substrate:cmake`. Only `bash` and `cmake` are in `_OPTIONAL_KEYS`, so only those two can be absent. A missing optional grammar makes the route resolve to nothing instead of raising. The C, C++, Python, Rust, and JS/TS grammars are treated as always present.
- Behind the routing, `_grammar_available` checks `substrate.has_language`, which calls `compiled_languages()` in `clew/substrate.py`. That reads the keys the installed `lang_parsing_substrate` wheel was compiled with.

**What happens on an installation whose parser lacks the grammars**

The index does not crash and does not silently go empty:

1. The substrate is not a version check. The fork that adds these grammars reports the same version string as the published wheel, so the code asks what is compiled in, not what version is installed.
2. With the published wheel, `compiled_languages()` lacks bash, cmake, yaml, and json. An unimportable substrate logs an error and yields no languages. The build does not fail.
3. Shell and CMake routes resolve to no grammar. The files are still registered and findable by name, but carry no symbols.
4. The build-time not-indexed report (`tests/test_not_indexed_report.py`) names the file types that were in scope but not read. For example: "14 `.sh` files were in scope and none of them are in this index." The query layer serves that stamp when an answer comes back empty. An index built before this release reports nothing rather than a fabricated empty set.

So an empty answer about a deploy script means one of three things: the symbol does not exist, the file type is not read by this build, or the file is outside the declared scope. The report is what tells you which.

**Caveats**

- I could not verify from the index which substrate this specific build was linked against. The `.yaml` path rows and the absence of `.sh` in scope are consistent with a substrate that has the grammars, but that is an inference.
- The index is not a census of the tree. A `.yaml` file that the index does not hold is absent by construction, not because it has no symbols.
- Symbols for shell and CMake only come from doc-commented or `function`/`macro` definitions, as the walkers recognise them. Data files never produce symbols, by design, so for YAML and JSON content questions the answer is "read the file directly."