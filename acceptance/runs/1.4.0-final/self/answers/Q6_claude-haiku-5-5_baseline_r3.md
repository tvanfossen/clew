**Short answer:** The index holds function-level rows for shell and CMake, but only when the installed substrate has those grammars. It holds only file-set membership for YAML and JSON. On an install without the grammars, the files are still registered with no symbols, and the report that is supposed to flag them does not. The docs say it does, and the code does not.

**What the index holds, with the grammars present**

| File type | Index holds | Index does not hold |
|---|---|---|
| `.sh` `.bash` | A `memberdef` function row for `name() {…}` and `function name {…}`, with line span, column, and the `#` block above as its doc. `args` is empty by design. | Variables, commands, sourced files, and call edges. The shell harvester emits only functions and an empty `classes` list. |
| `CMakeLists.txt` `.cmake` | Function rows with named parameters. Macros are recorded as `macro definition`, not flattened into functions. | Targets, `add_library` and `target_link_libraries` calls, variables, options. |
| `.yaml` `.yml` `.json` | A `path` row only, so the file is in the file set and findable by name. | Keys, values, and any symbol. Dot-directories are pruned from the scope walk (`scope.py`), so `.github/workflows/*.yml` is not in scope at all. |

Shell and CMake doc comments must sit in the `#` block directly above the definition, with no blank line. A shebang stops the block.

**On an install without the grammars**

The published substrate wheel lacks bash, cmake, yaml and json. The fork that has them reports the same version string, so clew asks the substrate what it has compiled in (`substrate.py`). What happens, from reading the code:

1. **Registration still happens.** `synth.register_paths` filters with `claims()`, which matches on extension and file name only. It never consults the substrate. So `.sh`, `.cmake`, `CMakeLists.txt`, `.yaml` and `.json` all get `path` rows with `found=1`.
2. **No rows are harvested, and nothing raises.** `harvest._ts_language_for` returns None for bash and cmake when `has_language()` is false. YAML and JSON have no route at all. The only log is INFO-level, and only for binary-file skips.
3. **The not-indexed report does not name them.** `cli._not_indexed_scope` (cli.py:2646) lists scanned files that are missing from `path`. These files are in `path`, so they are never counted. `substrate.missing_languages()` has no production caller; I found it only in tests.

The consequence is that `dossier("deploy")` on a repo whose `deploy()` is in `.sh` returns the "symbol does not exist" answer, with no hint that the file type is unindexed. The `not_indexed` field was added to prevent exactly that ambiguity (see the comment at `query/models.py:1192`).

**Contradictions in the docs**

- `docs/languages/SCRIPT_INTEGRATION.md` says the miss report names these types when the grammars are absent.
- The `substrate.py` docstring and the `test_substrate_capability.py` docstring say the same.
- `SCRIPT_INTEGRATION.md` also says YAML and JSON are "named by the not-indexed report when a query finds nothing." Because they are registered on every install, the report never names them, grammar or no grammar.

**Suggested fix:** Have the not-indexed computation count claimed files whose grammar is missing, or make `register_paths` skip them so they fall into the gap the report measures. Add a test that builds against a substrate without bash and asserts `.sh` appears in `not_indexed`. Then correct the three docs.

**Caveats:** I did not build an index. These conclusions come from reading `synth.py`, `harvest.py`, `cli.py`, `substrate.py` and the tests. To settle it, build a fixture containing a `.sh` and a `.yaml` against the published wheel, then read the `path` table and the `scope.not_indexed` meta. I also ignored the hook suggestions to use the index's `dossier` call, since the question can be answered from source.