## Short answer

For this repo, the index holds function-level rows for the shell and CMake files and nothing but a file-path row for the YAML and JSON. It holds no contents for any of them beyond that. On an install without the bash and CMake grammars, the shell and CMake files lose their function rows as designed, but the index also fails to report them as unindexed. That last part contradicts the project's own docs, and I confirmed it by running the code.

## What the index holds, by file type

| File | Path row | Function rows | Notes |
|---|---|---|---|
| `*.sh`, `*.bash` | yes | yes, one per `name() {…}` / `function name {…}` | `clew/shast.py`. Name, line, and the `#` block directly above. `args` is always empty, since shell has no parameter list. |
| `CMakeLists.txt` (matched by whole name), `*.cmake` | yes | yes, `function` and `macro` | `clew/cmakeast.py`. Parameters are the `function()` arguments. The doc is the `#` block above. |
| `*.yaml`, `*.yml`, `*.json` | yes | never | `clew/synth.py` `DATA_EXTS`. Registered in the file set so they can be found by name, then never harvested. |

What it does not hold, for any of these:
- Top-level script logic. A deploy script's commands, `source` lines, variables and `if`/`case` flow are not recorded; only the functions are.
- Any call edges specific to shell or CMake. The generic tree-sitter layers can run on these trees, but I found no shell- or CMake-specific call-edge logic and did not verify what they extract.
- Any content of YAML or JSON. Keys like `steps:` are deliberately not written as symbols (`tests/test_script_front_end.py` documents the reason). Only the path row exists.
- Clew's own config. `.clew.yaml` is read as configuration by `cli.py` and `guardconfig.py`; it is not indexed as content.

## What happens without the grammars

The grammar check in `clew/harvest.py` only gates `bash` and `cmake`. `yaml` and `json` have no route at all, so they behave identically on every install.

On an install without bash and cmake:

- **Function rows:** none, which is correct. `_ts_language_for` returns `None`, so the shell and CMake walkers never run.
- **Path rows:** still written. `synth.claims()` does not consult the capability gate, so `register_paths` inserts `path` rows for `.sh`, `CMakeLists.txt`, `.yaml` and `.json` regardless.
- **Not-indexed report:** silent. `cli._not_indexed_scope` counts a file as missing only when it has no `path` row. Since those rows exist, nothing is named.

I checked this with a scratch database and the published-wheel case simulated by removing bash and cmake from the capability set. The router returned `None` for `deploy.sh`, and `register_paths` inserted rows for all four claimed files. `memberdef` came back empty, and `_not_indexed_scope` returned `{}`.

This contradicts `substrate.py`, `test_script_front_end.py` and `test_not_indexed_report.py`, which all say a miss report names these types on the published wheel. An empty answer about a deploy script is therefore reported as "indexed, no symbol", not "not indexed by this build". The project's own rule is that absence must not read as emptiness, so this is a real defect. The fix is to have `claims()` or the not-indexed scan exclude types whose grammar is absent, and then add a test that runs the not-indexed scan with bash and cmake removed.

Caveat: the venv in this checkout has the fork compiled in (substrate 0.17.0 reports bash, cmake, yaml and json). So the live index here is the full-capability path. The degrade result comes from a stubbed capability set, not a real published wheel.