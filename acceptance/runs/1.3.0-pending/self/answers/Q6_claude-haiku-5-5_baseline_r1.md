**Short answer:** for shell and CMake the index holds function and macro definitions, with their `#` doc blocks. For YAML and JSON it holds only a file-set entry, with no symbols and no content. Doxygen reads none of the four. On an installation whose parser lacks the grammars, nothing crashes, but the file can still show up as indexed while holding no symbols, and the degrade message the design promises isn't wired up. I answered from source; I did not query a built index, and there is none in this directory.

**Doxygen never sees these files.** `DOXYGEN_DEFAULT_FILE_PATTERNS` (`clew/doxygen.py:203-257`) has no `.sh`, `.cmake`, `.yaml`, `.yml` or `.json`. Doxygen's own `FILE_PATTERNS` is forced to that list (gh#340), so a target's Doxyfile can't add them.

**What the index holds**

| File | Doxygen | Parse-built layer (`clew/synth.py`, `clew/harvest.py`) |
|---|---|---|
| `*.sh`, `*.bash` | nothing | `path` row, plus `memberdef` rows for `name() {}` and `function name {}` (`clew/shast.py`). `args` is empty by design. Doc is the `#` block directly above; a blank line breaks it. |
| `*.cmake`, `CMakeLists.txt` (matched by name) | nothing | `path` row, plus `memberdef` rows for `function` (kind `function`) and `macro` (kind `macro definition`). Parameters come from the argument list. `clew/cmakeast.py` |
| `*.yaml`, `*.yml`, `*.json` | nothing | `path` row only, `found=1`. No symbols, no prose, no docs. `DATA_EXTS` at `clew/synth.py:80` is registered but never harvested, on purpose: a `steps:` key would pollute the symbol namespace. `tests/test_script_front_end.py:161` pins this. |

**What it does not hold**

- **CMake's build graph.** Only `function_def` and `macro_def` are harvested (`cmakeast.py` `_DEFINITIONS`). Targets, `add_library`, `target_link_libraries`, `option()` and `set()` are not indexed, so "how is this target built" is not answerable from the index.
- **Shell's top-level logic.** Only function definitions are harvested. Statements, `source` edges and variables are absent.
- **CI and config content.** Workflow steps and `.clew.yaml` contents are not searchable as content. `.clew.yaml` sections are read as manifests (guard, threads, locks, shared keys, data model) and their content is hashed into stage cache keys (`clew/treescan.py` `manifest_key`), but that is configuration, not index content.
- **Prose.** Only `.md` and `.markdown` go into FTS (`clew/prose.py:47`).

**If the parser lacks the grammars**

The grammars are in a fork of lang-parsing-substrate. The published wheel has the same version string, so a fresh install can silently drop them (`tests/test_substrate_capability.py` docstring). Here is what happens:

1. `bash` and `cmake` are the only optional keys (`clew/harvest.py:145`). `_grammar_available` returns False, `_ts_language_for` returns None, and the file gets no tree and no rows. No crash.
2. `path` registration is by extension (`claims()`, `clew/synth.py:191-199`), not by grammar. So a `.sh` or `.cmake` file still gets a `path` row with zero symbols, and `.yaml`/`.json` rows are written on every install. The file looks indexed while holding nothing. That is the "absence is not emptiness" failure the project's own AGENTS.md warns about.
3. The promised report isn't wired up. `substrate.missing_languages` (`clew/substrate.py:72`) has no callers in `clew/`. The capability test's docstring says the miss report names these types as not indexed, but `clew/propose/notindexed.py` reports on scope, not grammars, so I found nothing that does that.
4. Non-optional keys (C, C++, Python, Rust, JS, TS) are not gated, so a substrate missing them fails loudly, as intended.

**What I checked:** the clew project venv at `/home/tvanfossen/Projects/clew/.venv` has substrate 0.12.0 with all five fork grammars (bash, cmake, yaml, json, markdown), confirmed by `parse_tree`. I did not run a build or a degraded install here, so point 2 is from reading the code, not a run.

**Suggested follow-up:** make `register_paths` skip script files whose grammar is absent, or record them as unparsed, and wire `missing_languages` into the build log. I haven't changed anything.