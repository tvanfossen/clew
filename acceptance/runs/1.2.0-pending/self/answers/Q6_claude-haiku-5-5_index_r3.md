Short answer: clew holds a shell or CMake definition as a function row, and holds a YAML or JSON file only as a registered path with no symbols. On an install without the bash or cmake grammar, shell and CMake files degrade the same way, silently, and the not-indexed report does not name them.

**What the index holds**

| File type | Rows written | Source |
|---|---|---|
| `.sh`, `.bash` | `memberdef` per `name() {}` / `function name {}`, docs from the `#` block above | `clew/shast.py`, `synth.py` |
| `CMakeLists.txt` (matched by name), `.cmake` | `memberdef` per `function()`, macros recorded as "macro definition" | `clew/cmakeast.py`, `synth.py` |
| `.yaml`, `.yml`, `.json` | one `path` row only, zero symbols | `synth.py` `DATA_EXTS` |

YAML and JSON are deliberate. Their grammars' "definitions" are keys and pairs, so writing them as symbols would bury real functions. `requirements.yaml` confirms this: the dossier returns a file with `harvested: true`, `symbol_count: 0`, empty documentation.

**What it does not hold**

- YAML and JSON content: keys, values, workflow steps, and CI jobs are never parsed. The `files` search corpus lists only parsed source, so these files are absent from it by construction.
- Shell top-level commands, variables, and CMake non-definition commands (`add_executable`, `target_*`): only function and macro definitions get rows. Shell functions get no parameter list because bash has none.
- Call edges from shell or CMake into the rest of the repo: I did not verify these.

**On an install without the grammar**

The router only gates `bash` and `cmake` (`_OPTIONAL_KEYS` in `clew/harvest.py`). Missing C, C++, Python, or Rust grammars fail loudly, by design.

For a missing `bash` or `cmake`:
1. `_ts_language_for` returns `None`.
2. `_harvest_one_file` returns `None`, so no payload and no `memberdef`.
3. `register_paths` still writes a `path` row, because `claims()` never checks grammar availability. The file stays findable and looks indexed.
4. `_not_indexed_scope` in `clew/cli.py` counts only files with no `path` row. A `.sh` file on a bash-less install is therefore absent from `not_indexed`, and the report stays silent about it.

That fails the repo's own absence-is-emptiness rule. I read this from code and did not run a build without bash to confirm it. The fix would be to name claimed-but-ungrammared files in the report, or to write a path row that says "no grammar" distinctly from "parsed, nothing found".

YAML and JSON never reach a grammar at all, so their presence does not depend on the substrate.

**Caveats from this checkout**

- This repo has no `.sh` or `CMakeLists.txt` files, so I could not query shell or CMake rows live. Those conclusions come from the harvester source and its tests.
- `.github/workflows/ci.yml` returns a definitive not-found. That is scope, not the parser: `scope.py` `_skip_dir` prunes every dot-directory by default, and `.clew.yaml` declares no index scope.
- The local clew venv's substrate compiles in `bash`, `cmake`, `json`, and `yaml`. The skip message in `tests/test_script_front_end.py` and the note in `.claude/tmp/substrate-fork.md` indicate the published substrate lacked `bash` and `cmake`, so a stock install is the case where the degradation applies.