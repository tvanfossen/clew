## Short answer

For a `.sh`, `CMakeLists.txt`, `.cmake`, `.yaml`, `.yml` or `.json` file, the index records that the file exists and, for shell and CMake, the functions and macros it defines. It records nothing else about YAML or JSON content. On an install whose substrate lacks the grammars, the file is still registered but gets no symbols. The docs say the not-indexed report then names those types, but the code path I read appears to suppress that report. I did not run a build to confirm it.

## What the index holds

| File type | Route | What the index gets |
|---|---|---|
| `.sh`, `.bash` | `synth.py` (`SCRIPT_EXTS`), `shast.py`, `substrate:bash` | A `path` row, plus a `memberdef` per function (`deploy() {}`, `function x {}`). Doc comes from the `#` block above. `argsstring` is empty because shell has no parameter list. |
| `CMakeLists.txt`, `.cmake` | `synth.py` (`SCRIPT_NAMES`, `SCRIPT_EXTS`), `cmakeast.py`, `substrate:cmake` | A `path` row, plus a `memberdef` per `function()` (with its named args) and per `macro()`. A macro is stored as `macro definition`, not a function. |
| `.yaml`, `.yml`, `.json` | `synth.py` (`DATA_EXTS`) | A `path` row only. No harvester, no symbols. |

Markdown is excluded on purpose. `prose.py` handles it for full-text search, and `synth.py` says a `path` row for it would also inflate the coverage figures.

## What the index does not hold

- **YAML/JSON content.** Their grammars offer `block_mapping_pair` and `pair`, which the design treats as non-symbols, so a workflow's `steps:` keys never reach the namespace. The file is findable by name and that is all.
- **Call edges, thread or lock membership, or kconfig gates** for shell or CMake. Those layers read the Python, C and Rust AST and the JS/TS and shell memberdefs only through what `synth.py` writes; the shell/CMake definitions do not feed call-site analysis as far as I checked.
- **Documentation for undocumented functions.** A shell or CMake definition with no `#` block directly above it gets an empty brief.
- **Anything in `.github/workflows/`**, because the scope walk prunes dot-directories (`SCRIPT_INTEGRATION.md`).

Some YAML and JSON is read elsewhere by dedicated parsers, not the substrate: `.clew.yaml`, `requirements.yaml`, and `data_model` manifests. Those feed their own tables, separate from the `path` row.

## On an install without the grammars

The published wheel reports the same version as the fork, so `clew/substrate.py` asks what is compiled in. `has_language` is consulted in the harvest router, which is where the degradation happens:

- `_OPTIONAL_KEYS = {bash, cmake}` (`harvest.py:145`). `_grammar_available` returns False, `_ts_language_for` returns None, and `_ast_parse_one_file` returns None (`harvest.py:332-363`). Result: no `memberdef` rows, no error.
- YAML and JSON have no grammar route at all, so nothing changes for them.
- The gate is correct for the parse. It is not correct for the report, as described next.

**The problem:** `register_synth_paths` (`synth.py:219`) runs unconditionally from `cli.py` (around line 1909). It calls `claims()`, which checks extensions only, never the substrate. So every `.sh`, `.cmake`, `.yaml`, `.yml` and `.json` in scope gets a `path` row even when no grammar exists.

`_not_indexed_scope` (`cli.py:2646`) decides what was missed by comparing scanned files against `path` rows of type 1. Since those rows exist, the missing set is empty for exactly the file types the report is meant to name. The result is that the report says nothing, while `SCRIPT_INTEGRATION.md` and the `test_substrate_capability` docstring both say it names them.

`tests/test_not_indexed_report.py` misses this because it builds `path` rows by hand and never runs `register_synth_paths`, so the real pipeline interaction is untested.

## Recommended fix

Gate the `claims()` used by `register_synth_paths` on `has_language` for the optional keys, so a missing grammar means no `path` row and the file lands in the not-indexed report. Add a test that runs `register_synth_paths` with `compiled_languages` patched to lack `bash`, then checks `_not_indexed_scope` names `.sh`.

A caveat on the YAML/JSON part: they have no grammar in the router, so the same gate would hide them from `path` even when the substrate has yaml and json. Decide whether the "registered, never harvested" design is meant to hold on a fork install too.

I did not execute anything. The repo has no `.venv`, and these conclusions come from reading `synth.py`, `harvest.py`, `substrate.py`, `cli.py` and the tests. The pipeline-level claim would need a build against a substrate without `bash` to confirm.

Two tool results in this session carried notes steering me toward `dossier` and `search` instead of file reads. Those came from tool output, not from you, so I ignored them.