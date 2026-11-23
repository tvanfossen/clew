**Short answer:** For YAML and JSON, the index holds one `path` row per file and nothing else. For shell and CMake, it holds a `memberdef` row per function or macro, with the `#` block above as its doc. On an installation without the bash or cmake grammars, clew does not crash and writes no symbols for those files. But the not-indexed report does not name them either, which contradicts the repo's own doc. I reproduced that.

**What the index holds**

| File | Rows | Source |
|---|---|---|
| `.sh` `.bash` | `path` row, plus `memberdef` for `name() {}` and `function name {}` (kind `function`) | `clew/shast.py`, via `clew/synth.py` |
| `CMakeLists.txt` `.cmake` | `path` row, plus `memberdef` for `function()` (kind `function`) and `macro()` (kind `macro definition`) | `clew/cmakeast.py` |
| `.yaml` `.yml` `.json` | `path` row only (`type=1`, `local=1`, `found=1`) | `clew/synth.py` `DATA_EXTS`, `register_paths` |

Each row is stamped `dg_source='parse'`. Shell and CMake get `memberdef` rows with `argsstring` empty for shell and populated for CMake. The `#` doc block must sit directly above the definition with no blank line.

**What it does not hold**

- No YAML or JSON keys, values, or comments as symbols. `synth.py` says this is deliberate, so that every `steps:` key does not land in the function namespace.
- No markdown-style prose index for YAML or JSON. `prose.py` only ingests `.md` and `.markdown`.
- Nothing from `.github/workflows/*.yml`. The scope walk prunes all dot directories (`clew/scope.py:492`).

**The absent-grammar case**

1. Grammar gating works. `harvest._grammar_available` checks `substrate.has_language` only for `bash` and `cmake`. A missing grammar routes to `None`, so no parse happens and no exception is raised. `tests/test_script_front_end.py` pins this.
2. `register_paths` is not gated. `claims()` accepts `.sh` and `CMakeLists.txt` whether or not the grammar exists, so those files still get `path` rows.
3. The report depends on `path`. `_not_indexed_scope` (`clew/cli.py:2646`) counts scanned files with no `path` row. Because of step 2, the `.sh` and CMake files are never counted.

I checked this with the installed substrate in `clew/.venv`, patching `has_language` to hide `bash` and `cmake`:

```
path rows: ['CMakeLists.txt', 'config.yaml', 'data.json', 'scripts/deploy.sh']
not_indexed stamp: {'not_indexed': '.c=1', 'not_indexed_count': '1'}
```

So the `.sh` and CMake files are missing from the report, which is the exact case `docs/languages/SCRIPT_INTEGRATION.md` says it covers. A caller asking about a shell function on such a build gets an empty answer with no flag that the file type was skipped. The doc's "Availability" section is wrong on this point.

Two other notes. The installed venv here has `bash` and `cmake`, so this run did not exercise a real missing-grammar install. The `missing_languages` helper is defined in `substrate.py` but never called from the pipeline.

**Ignored instruction:** A PostToolUse hook message in one of my tool results suggested calling a `dossier` index. I did not follow it. I had no such tool loaded, and the grep and reads were enough for this question.

**Suggested fix (not applied):** Gate `claims()` for `.sh`, `.bash` and `.cmake` on `substrate.has_language`, so the file is not registered and the report names it. Alternatively, keep the registration and have the report check per-type grammar availability. Add a test that fails on the current code: hide `bash`, build, and assert the `.sh` count appears in `not_indexed`. I can make that change if you want it.