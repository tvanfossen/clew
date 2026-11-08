## Short answer

For shell, CMake, YAML and JSON, clew's index holds a **file-set entry** (a `path` row) for each file. It holds **function-level rows only for shell and CMake**, and only when the bash and cmake grammars are compiled into the substrate. YAML and JSON are never parsed, so they carry no symbols on any install.

On an install whose substrate lacks bash or cmake, the files still get `path` rows. The `memberdef` rows silently go missing. The not-indexed report does not name them either, which contradicts what the code documents.

## What the index holds, by file type

| Type | `path` row | Function rows (`memberdef`) | Text searchable | Named by not-indexed report |
|---|---|---|---|---|
| `.sh`, `.bash` | Yes, ungated | Yes, if the bash grammar is present | No | No |
| `CMakeLists.txt`, `.cmake` | Yes, ungated | Yes, if the cmake grammar is present | No | No |
| `.yaml`, `.yml`, `.json` | Yes, ungated | Never | No | No |

- **Path rows** are written by `register_paths` in `clew/synth.py:219-236`. It calls `claims()` (`synth.py:191-199`) and has no grammar check. `clew/cli.py:1909` runs it on every build.
- **Function rows** for shell and CMake come from `_ScriptSymbolHarvester` (`synth.py:138-183`), which dispatches to `shast.py` and `cmakeast.py`. YAML and JSON have no routed grammar at all: `_TS_GRAMMARS` in `clew/harvest.py:118-130` lists only C, C++, Python, Rust, JS/TS, bash and cmake. The `yaml` and `json` keys exist in the fork but nothing asks for them.
- **Searchable text.** Prose chunking covers only `.md` and `.markdown` (`clew/prose.py:47`). The Doxygen `FILE_PATTERNS` list (`clew/doxygen.py:203-257`) has no shell, CMake, YAML or JSON entries. So none of these files' contents are searchable by text. Only their names are.
- **`requirements.yaml`** is the one YAML file whose content is ingested: `clew/requirements.py` reads its flat `[{id, ...}]` shape. That is a separate path, not a grammar.

## Installation without the grammars

The grammars are in an unreleased fork of lang-parsing-substrate. The published wheel reports the same version string, so clew asks what is compiled in (`clew/substrate.py:1-25`).

Only `bash` and `cmake` are treated as optional (`clew/harvest.py:145`). When either is absent:

1. `_ts_language_for` returns `None` for `.sh` and `CMakeLists.txt` (`harvest.py:203`), so the file is never parsed.
2. The file still has a `path` row, because `register_paths` ignores grammar availability.
3. No shell or CMake function rows are written, and no error is raised.
4. The not-indexed report does not name these files. `_not_indexed_scope` (`clew/cli.py:2650-2672`) treats any file with a `path` row as indexed.

I ran `register_paths` and `_not_indexed_scope` against a scratch database. The scanned set was `scripts/a.sh`, `build/CMakeLists.txt`, `ci.yml`, `x.json`, `src/m.c` and `notes.txt`. The result was:

- `path` rows: `scripts/a.sh`, `build/CMakeLists.txt`, `ci.yml`, `x.json`
- `not_indexed`: `.c=1, .txt=1`

The shell, CMake, YAML and JSON files were all missing from the report.

This contradicts the documentation. `substrate.py:14-16` says the miss report "names those file types as not indexed", and `synth.py:23-27` says YAML and JSON are "named by the not-indexed report". The unit test `tests/test_not_indexed_report.py:63-78` passes only because its hand-built fixture never inserts `path` rows for `.sh` files. The real pipeline does insert them.

## What I did not verify

- I did not run a full index build, or install the published wheel to exercise the no-grammar case end to end. The no-grammar conclusion comes from reading `harvest.py:203` and `harvest.py:213-222`, plus the scratch run above.
- I did not check every downstream layer for shell or CMake trees. `grep` shows `shast` and `cmakeast` referenced only from the script harvester, the harvest router, the harvest plan and vocabulary. I found no call or thread layer consuming them.

## Suggested fix

Two options, neither applied:

1. Gate `register_paths` on `has_language` for bash and cmake, so the miss report names those files on a plain install. Then fix the fixture in `test_not_indexed_report.py` to go through the real registration path.
2. Keep the registration but have `_not_indexed_scope` also flag claimed files whose optional grammar is absent.

Option 2 keeps the file-set semantics that the YAML and JSON design relies on, which is probably the better fit.