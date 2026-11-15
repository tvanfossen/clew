**Short answer:** For shell and CMake, the index holds one row per function or macro definition, with its name, doc block and (for CMake) parameters. For YAML and JSON it holds only a `path` row, so the file is known to exist and nothing inside it is searchable. On an install whose substrate lacks the bash or cmake grammar, shell and CMake degrade to path-only rows. The docs say the not-indexed report then names those types, but in a real build it does not. I checked that in code.

**What the index holds, by file type**

| File | Rows written | Source |
|---|---|---|
| `*.sh`, `*.bash` | `memberdef` per `name() {}` or `function name {}`; args empty; doc from the `#` block directly above | `clew/shast.py`, `clew/synth.py` |
| `CMakeLists.txt`, `*.cmake` | `memberdef` per `function()`, with `argsstring`; `macro()` gets `kind = 'macro definition'` | `clew/cmakeast.py` |
| `*.yaml`, `*.yml`, `*.json` | `path` row only | `clew/synth.py:80`, `register_paths` |

Matching is by whole path component for `CMakeLists.txt`, so `.txt` in general is not claimed. Definition rows are stamped `dg_source='parse'`.

**What it does not hold**

- Shell top-level commands, call edges out of scripts, and variables. Only definitions are harvested.
- YAML or JSON keys and values. A YAML key is a `block_mapping_pair` and is deliberately not a symbol, to keep `steps:` out of the function namespace.
- Any file-level doc for shell or YAML. `filedocs.py` has no extractor for `.sh` or `.yaml`, so the `#` header is used only for per-function docs.
- `.github/workflows/*.yml`, because the scope walk prunes dot directories.
- YAML as indexed content. clew reads `.clew.yaml` and data-model manifests as configuration, so the index holds facts derived from them, not the files.

**On an install without the grammars**

- YAML and JSON are never routed to a grammar in `_TS_GRAMMARS` (`clew/harvest.py`), so they behave the same with or without the substrate's `yaml`/`json` keys.
- `bash` and `cmake` are gated by `_OPTIONAL_KEYS`. With them absent, `_ts_language_for` returns None, so `.sh` and CMake files get path rows and no symbols. I confirmed this by stubbing `has_language` to False: `deploy.sh`, `CMakeLists.txt`, `x.cmake` route to None, and `a.c` still routes.
- Nothing raises, and the rest of the build proceeds.

**The finding: the not-indexed report misses these files in a real build**

`docs/languages/SCRIPT_INTEGRATION.md` says that with a lacking substrate, "the not-indexed report … names those file types." The code does not do that:

1. `cli.py:1909` calls `register_synth_paths` unconditionally, before `_not_indexed_scope` (`cli.py:2263`).
2. `register_paths` writes a `path` row for every claimed file, including `.sh`, `.cmake`, `.yaml`, `.yml`, `.json`, whether or not a grammar exists.
3. `_not_indexed_scope` treats "has a `path` row" as "indexed", so these files are never counted as missing.

I reproduced this in a temp DB with the venv's `clew` code. Scanned files `deploy.sh`, `x.cmake`, `CMakeLists.txt`, `app.yaml`, `app.json`, `a.c`, `notes.md` produced `not_indexed = ".c=1, .md=1"`. The shell, CMake and data files were not reported.

The tests do not catch this. `tests/test_not_indexed_report.py` builds its DB with explicit path rows and never runs `register_paths`, so its `.sh=3` expectation is not exercised through the real build order.

The consequence is that a query about a deploy script on a degraded install returns empty with no signal that the file was in scope but unread. That is the case the report was meant to prevent.

**Caveats**

- I did not run a full `clew index` on a degraded substrate. The findings come from reading the code and from the two simulations above.
- The venv's substrate has all five keys (`bash`, `cmake`, `yaml`, `json`, `markdown`). The module docstring says the published wheel lacks them. I did not check the published wheel.
- I did not verify that the other harvest stages leave bash trees alone once the bash grammar is routed.