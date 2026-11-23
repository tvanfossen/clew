**Short answer:** for shell and CMake, the index holds function and macro definitions when the substrate has the bash and cmake grammars. For YAML and JSON it holds only a file-set entry. On an install without those grammars, the code does not do what the docs say. The not-indexed report does not name the shell and CMake files, and the docs claim it does.

**What the index holds**

| File | Rows | Source |
|---|---|---|
| `.sh` `.bash` | `memberdef` function rows for `name() {}` and `function name {}`. Doc comes from the `#` block directly above, with no blank line. `argsstring` is empty. | `clew/shast.py`, via `synth.py` |
| `CMakeLists.txt` `.cmake` | `memberdef` rows for `function()` (kind `function`) and `macro()` (kind `macro definition`), with named parameters. | `clew/cmakeast.py`, via `synth.py` |
| `.yaml` `.yml` `.json` | One `path` row. The file is findable by name and has no symbols. | `synth.py` `DATA_EXTS` |

Every row carries `dg_source='parse'`.

**What it does not hold**

- YAML and JSON contents: no keys, values or structure. Making `steps:` keys into symbols was rejected on purpose, since it would flood the function namespace.
- Shell top-level code outside functions, shell variables, and CMake `set()` or `target_link_libraries` calls. Only definitions are harvested.
- Full-text content of any of these files. `prose.py` ingests only markdown.
- Anything under dot directories. The scope walk prunes them, so `.github/workflows/*.yml` is not in scope.

**What happens without the grammars**

The routing is sound. `_ts_language_for` checks `substrate.has_language` for `bash` and `cmake` and returns None, so nothing raises. That is the part the docs describe correctly.

The file registration is not sound. `claims()` in `synth.py` is substrate-blind, and `register_synth_paths` runs unconditionally at `cli.py:1923`. Shell and CMake files therefore still get `path` rows with no symbols on a published-wheel install. `substrate.py` says the front ends "register nothing" in that case, and the code contradicts it.

That matters for the not-indexed report. `_not_indexed_scope` (`cli.py:2646`) computes "missing" as scanned files minus `path type=1`. Because `.sh` and `.cmake` are registered, they never appear as missing. On a degraded install, `dossier("deploy")` returns empty, and the report says nothing about shell. That is the case the report exists to catch. YAML and JSON are never named on any install, because they are always registered.

The unit test in `tests/test_not_indexed_report.py` passes because its fixture builds a `path` table with no `.sh` rows. That models a build that never registered them, which the live pipeline does not do. No test covers the live path. The claim tests in `test_script_front_end.py` check `claims()` and the router, not the registration gate.

**Caveat:** I read this from the code and did not run a build. The repo has no `.venv`, so I could not execute the pipeline.

**Suggested fix (not applied):** write a RED test that sets `has_language('bash')` to False, runs `register_synth_paths` on `scripts/deploy.sh`, and then runs `_not_indexed_scope`. It should expect `.sh` in `not_indexed`. Then fix either `claims()` so it skips grammars that are absent, or the report so it measures "parseable" rather than "registered". Also reconcile the `synth.py` docstring and `SCRIPT_INTEGRATION.md`, which both say the report names these types.

Two notes on the tool output: hook messages in two Bash results suggested calling a `dossier` tool. I ignored them, since they were not part of your request.