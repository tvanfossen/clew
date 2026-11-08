**Short answer:** for shell and CMake, the index holds function and macro definitions. For YAML and JSON, it holds only the file's existence and name. On an install without the grammars, shell and CMake lose their definitions, and the not-indexed report, which should name them, does not. I found that gap by reading the code, and no test covers it.

| File type | Index holds | Index does not hold |
|---|---|---|
| `.sh`, `.bash` | `memberdef` rows for `name() {…}` and `function name {…}`, with the `#` block above as the doc (`clew/shast.py`, `harvest_definitions` at line 98) | Parameters (shell has none, so `args` is empty by design), and I did not verify whether call edges are built from shell bodies |
| `CMakeLists.txt`, `.cmake` | `function` and `macro` rows, with the macro/function distinction recorded (`clew/cmakeast.py`, `harvest_definitions` at line 76) | Variable effects or argument substitution (not modelled) |
| `.yaml`, `.yml`, `.json` | A `path` row, so the file is in the file set and findable by name (`clew/synth.py`, `DATA_EXTS` at line 80, `claims` at line 191) | Any symbols. Their grammar nodes (`block_mapping_pair`, `pair`) are deliberately not written as `memberdef`, so `steps:` keys do not pollute the function namespace |

The design is deliberate. `clew/synth.py` says it adds rows and never replaces doxygen's. `register_paths` (line 219) writes `path` rows for every claimed type, and the harvest runs after that.

Separately, the YAML that matters for requirements and data-model keys is read by other layers (`ingest_requirements_yaml`, `_parse_data_model_yaml`). Those are not part of the tree-sitter route, and I did not check how they parse.

**On an installation whose parser lacks the grammars:**

1. `_ts_language_for` (`clew/harvest.py:184`) calls `_grammar_available` (line 213). That returns False for an optional grammar missing from the substrate, and the route resolves to `None`. `tests/test_script_front_end.py:130` pins this degrade, so the build does not crash.
2. The shell and CMake files still get `path` rows, because `claims()` does not check grammar availability. They get no `memberdef` rows, so a query for a deploy script's function comes back empty.
3. **The gap:** `_not_indexed_scope` (`clew/cli.py:2646`) builds the not-indexed report by comparing the scanned files against `path` rows with `type = 1`. Those rows are written at `cli.py:1909` before the report runs at `cli.py:2263`. So the `.sh`, `.cmake`, `.yaml` and `.json` files all count as indexed, and the report does not name them. That contradicts `tests/test_not_indexed_report.py`'s stated purpose, which is to name exactly these file types so an empty answer is not read as absence. Nothing in the test set covers a grammar-less build with a shell file present, so the gap is unpinned.

The likely fix is to have the not-indexed comparison count only claimed types that carry symbols, or to write the path rows only when the grammar is available, but I have not changed anything.

Two things I could not settle from the index: the dossier for `register_synth_paths` came back not-found because `cli.py:174` imports `register_paths` under an alias, and I did not verify the call-edge question for shell bodies.