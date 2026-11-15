**Short answer:** For the four file types, the index holds different things. Shell and CMake get real definition rows, when the grammar is present. YAML and JSON get a file-set entry and nothing else. On an install without the grammars, the docs say the shell/CMake files are "named by the not-indexed report." My probe found that the report does not name them, which contradicts the docs.

**What the index holds (grammar present)**

| File | Rows | Detail |
|---|---|---|
| `.sh` `.bash` | `memberdef` for `name() {}` and `function name {}` | Doc comes from the `#` block directly above. No args, since shell has no parameter list. |
| `CMakeLists.txt` `.cmake` | `memberdef` for `function()` and `macro()` | A macro is stored as `macro definition`, not as a function. Named args are reported. |
| `.yaml` `.yml` `.json` | `path` row only | Findable by name in `search(corpus='files')`. Zero symbols, by design. |

Evidence: `clew/synth.py` (`SCRIPT_EXTS`, `DATA_EXTS`, `emit_definitions`), `clew/shast.py`, `docs/languages/SCRIPT_INTEGRATION.md`. The live index lists 16 YAML files and 16 JSON files as file rows with `symbol_count: 0`.

**What it does not hold**

- YAML and JSON keys. Writing them as symbols would put every `steps:` key of every workflow into `dossier` lookups.
- Anything in `.github/workflows/`. The scope walk prunes dot directories, so CI workflows are out of scope on every tier.
- Shell variables, `source`d files, or call sites. Only definitions are harvested. I did not find a shell call-edge harvest, so I'm treating that as absent.
- CMake targets, `add_executable`, `target_link_libraries` or variables. The walkers recognise only function and macro definitions.
- Markdown is prose, handled by a separate path.

**An installation whose parser lacks the grammars**

The docs say the answer is "registered in the file set, no symbols, no error, and the not-indexed report names the types." The code agrees with the first two parts:

- `claims()` in `clew/synth.py` does not check the grammar, so `register_paths` writes `path` rows for `.sh`, `CMakeLists.txt`, `.yaml` and `.json` regardless.
- `_ts_language_for` returns `None` for a missing optional grammar (`_OPTIONAL_KEYS = {"bash", "cmake"}` in `clew/harvest.py`), so no definitions are harvested. Nothing raises.

The third part fails. `_not_indexed_scope` in `clew/cli.py` lists as missing only the scanned files with no `path` row. Because `register_paths` already gave the shell and YAML files rows, they are never counted as missing.

I ran this against the repo's own code, with `bash` and `cmake` masked and no doxygen rows:

```
registered: 4
path rows: ['CMakeLists.txt', 'config.yaml', 'data.json', 'scripts/deploy.sh']
not_indexed: {'not_indexed': '.c=1', 'not_indexed_count': '1'}
```

The `.c=1` only appears because my probe had no doxygen rows for C. The shell, CMake and YAML files are not reported. An empty answer about a deploy script would therefore give no hint that the file was unread. The test in `tests/test_not_indexed_report.py` misses this because it hand-builds a `path` table without the shell or YAML rows. Also, `test_shell_and_cmake_definitions_become_rows` and the doc-block test skip rather than fail when the grammar is absent, so a no-grammar install passes green.

**Fix options (your call):** make `claims()` or `register_paths` skip shell and CMake rows when `has_language` is false, so the report names them. Or have the report compare against harvested rows, not `path` rows. I'd take the first, since the docs already describe that behaviour. I have not changed anything.

**Not verified:** how the live emptiness reply (`clew/mcp_server/emptiness.py`) builds its "covered shape" for these types. I only checked the report-stamping path.

**Housekeeping:** I created `.claude/tmp/no_grammar_probe.py` for the probe. Deleting it was denied, so it is still there and can be removed with `rm`.