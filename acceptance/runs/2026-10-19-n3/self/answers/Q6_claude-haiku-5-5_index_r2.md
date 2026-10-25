**Short answer:** for shell and CMake, the index holds function and macro definitions with their `#` doc blocks. For YAML and JSON it holds only a `path` row, so the files are findable by name but contribute no symbols. On an installation whose substrate lacks the grammars, nothing raises: the shell and CMake files stay registered with no symbols, and the not-indexed report is meant to say so. I did not confirm that last step at runtime because this repo has no `.venv`.

**What the index holds, by file type**

| File type | Routing | What the index gets |
|---|---|---|
| `.sh`, `.bash` | `_SH_EXTS` → `substrate:bash` (`clew/harvest.py:98,126`) | `memberdef` rows for `f() {}` and `function f {}`, documented by the `#` block above |
| `CMakeLists.txt`, `.cmake` | `_NAME_GRAMMARS` for the whole name, then `_CMAKE_EXTS` → `substrate:cmake` (`harvest.py:104–133`) | `function()` as a function, `macro()` as `macro definition`, with named arguments |
| `.yaml`, `.yml`, `.json` | `register_paths` claims them (`clew/synth.py:80,226`) | A `path` row only, so they are in the file set and named by the miss report. Never harvested, no symbols |
| `.md` | Not a symbol source | Chunked into the prose full-text corpus (`clew/prose.py`) |

**What it does not hold**

- YAML and JSON carry no symbols by design. Their grammars offer `block_mapping_pair` and `pair`, and writing those as symbols would flood `dossier` with every `steps:` key. (`synth.py:71–75`, `docs/languages/SCRIPT_INTEGRATION.md`)
- Any file in a dot directory is pruned by the scope walk, so `.github/workflows/*.yml` is not in scope on any tier (SCRIPT_INTEGRATION.md, "Scope note").
- Shell has no parameter list, so shell functions get empty `argsstring`. That is a language fact, not a harvest gap.
- Calls made from shell or CMake into C are not resolved as call edges. I did not verify this in code, so treat it as unconfirmed.

**What happens without the grammars**

- `_OPTIONAL_KEYS` is `{"bash", "cmake"}` (`harvest.py:145`). `_grammar_available` checks `substrate.has_language`, and when it is false `_ts_language_for` returns `None` (`harvest.py:184–207`). The file is then skipped, with no exception.
- `register_paths` is not gated on the substrate. Shell, CMake, YAML and JSON files still get `path` rows, so they appear in the file set with zero symbols.
- `compiled_languages()` logs an ERROR and returns an empty set if the substrate cannot be imported. Every optional route then fails closed, and that failure shows in the logs.
- The docs say a miss on such an install should name the file types it did not read, not return a bare negative (`tests/test_not_indexed_report.py`, `docs/languages/SCRIPT_INTEGRATION.md`). That is the designed behaviour. I did not confirm the report text in code.

**Inconsistencies I noticed**

- `_ts_language_for`'s brief still says it selects "C, C++, Python or Rust" and omits the newer languages, so its docs are stale.
- `docs/languages/SCRIPT_INTEGRATION.md` says YAML and JSON are "a `path` row: in the file set", which matches the code. `tests/test_substrate_capability.py` says the fork registers YAML and JSON grammars, but `harvest.py` never routes to them. Nothing parses YAML or JSON, so this is harmless in practice, but the two statements do not line up.