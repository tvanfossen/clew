## Short answer

The index holds a `path` row for every YAML and JSON file, so they are visible by name. It holds `memberdef` rows for shell functions and CMake functions and macros, with doc blocks taken from the `#` comments above them. It holds nothing about what the files configure: no keys, values, or structure. On an installation whose substrate lacks the bash and cmake grammars, the design says shell and CMake files degrade to "registered, no symbols, named in the miss report." My probe found the miss report does not name them, so that part of the design is broken.

## What the index holds, by file type

| File | `path` row | Symbols | Doc source | What it does not hold |
|---|---|---|---|---|
| `.sh` `.bash` | yes | `memberdef` per `name() {}` or `function name {}` | `#` block directly above, no blank line | Top-level commands, variables, `source` chains, `$1`-style args (empty by design) |
| `CMakeLists.txt` `.cmake` | yes | `memberdef` per `function()`; `macro()` as `kind = 'macro definition'` | `#` block above | `add_executable`/`add_library` targets, `set()` variables, `option()` |
| `.yaml` `.yml` `.json` | yes | none | none | Keys, values, `steps:` entries, CI job names, anything structural |

Relevant code: `clew/synth.py` (`SCRIPT_EXTS`, `DATA_EXTS`, `register_paths`, `emit_definitions`), `clew/shast.py`, `clew/cmakeast.py`, and `docs/languages/SCRIPT_INTEGRATION.md`.

Other facts:
- YAML and JSON are deliberate non-symbols. Their grammars expose `block_mapping_pair` and `pair`, and writing those as symbols would flood the namespace with every `steps:` key.
- Markdown is excluded from `path` on purpose. It goes to the prose corpus instead.
- The scope walk prunes dot directories, so `.github/workflows/*.yml` is not in scope on any tier. Only YAML under `conf/`, `deploy/`, or the root is indexed.
- Call edges for shell are unverified. The docs say call edges "work on them unchanged," but `call_edges.py` has no bash-specific walker. I found no evidence that shell call sites produce edges.

## What happens without the grammars

The intended behaviour, per `clew/substrate.py` and `clew/harvest.py`:
- `_OPTIONAL_KEYS = {"bash", "cmake"}` means a missing grammar routes to `None` and nothing raises.
- A `.sh` or CMake file gets no symbols.
- `_not_indexed_scope` in `clew/cli.py` should list the file types with no `path` rows, so an empty answer tells the caller to read the file.

**The gap:** `claims()` and `register_paths()` in `synth.py` never consult the substrate. They register `.sh` and `CMakeLists.txt` as `path` rows whether or not bash or cmake is compiled in. `_not_indexed_scope` counts only scanned files that lack a `path` row, so those files are never reported.

I checked this by running the repo's code from its own directory, using the clew venv's interpreter and substrate. I monkeypatched `compiled_languages()` to a set without bash or cmake, which simulates the published wheel. This is a simulation, not a real published install. Results:

```
bash route:  None
cmake route: None
path rows:   ['.github/workflows/ci.yml', 'CMakeLists.txt', 'conf/a.yaml', 'conf/b.json', 'scripts/deploy.sh']
not_indexed: {'not_indexed': '.c=1', 'not_indexed_count': '1'}
```

`deploy.sh` and `CMakeLists.txt` are registered but carry no symbols, and the report says nothing about them. A `dossier("deploy")` on that install comes back empty with no statement that the file type was skipped. That is the silent gap the design was meant to prevent.

The test `tests/test_not_indexed_report.py` does not catch this. Its fixture builds a `path` table by hand that holds only `.c` rows, so it never exercises the real registration path.

## Suggested fix (not applied)

Gate the script claims on the substrate, so that a missing grammar means no `path` row. The miss report would then name `.sh` and `.cmake` correctly. Add a test that runs `register_paths` against a `compiled_languages` stub without bash and asserts the report names `.sh`. Separately, either implement shell call edges or remove the claim from the docs. I have not changed any files.