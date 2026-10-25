**Short answer:** for shell, CMake, YAML and JSON, the index holds a `path` row for every file, on any install. Shell and CMake also get `memberdef` rows for their functions and macros, but only when the bash or cmake grammar is compiled in. YAML and JSON never get symbols. Without the grammars, the build degrades rather than crashes. The miss report does not say so, though, which contradicts what the code comments claim.

**What the index holds** (`clew/synth.py`, `clew/harvest.py`, `clew/filedocs.py`)

| | `.sh` / `.bash`, `.cmake`, `CMakeLists.txt` | `.yaml` / `.yml` / `.json` |
|---|---|---|
| `path` row (in file set, findable by name) | Yes, always. `register_paths` calls `claims()` and never checks the grammar. | Yes, always. |
| `memberdef` rows for functions and macros, with docs from the `#` block | Only if the grammar is compiled in. `_OPTIONAL_KEYS` gates `bash` and `cmake`. | Never. There is no route in `_TS_GRAMMARS` and no harvester. |
| Call edges, threads, locks | Only from those `memberdef` rows | None |
| `file_docs` / prose | No. `filedocs` has no extractor for these suffixes. | No |
| Keys, values, script bodies | No | No |

Files classified as binary by `clew/filetypes.py` are skipped before any of this runs.

Two more points:
- The YAML/JSON grammars in the fork are unused by clew. Even with the fork installed, YAML and JSON still get no symbols, because nothing routes to them.
- `.clew.yaml`, `requirements.yaml` and the data-model YAML are read with PyYAML (`declaration.py`, `requirements.py`, `datamodel.py`), not through the substrate. Their effects land in scope and requirements data, not in rows about the YAML file.

**An install without the grammars** (the published `lang-parsing-substrate` 0.11.2 wheel, per `clew/substrate.py`)
- `_ts_language_for` returns None for `.sh` and `.cmake`. The harvest skips them, so they get `path` rows but no `memberdef` rows, and nothing raises.
- Always-present grammars (C, C++, Python, Rust, JS, TS) are deliberately not gated, so a broken install still fails loudly.
- **Discrepancy:** `substrate.py` (lines 8–10) and `tests/test_substrate_capability.py` say the front ends register nothing and the miss report names these types as not indexed. The code does not match. `register_paths` never calls `has_language`, so `.sh` and `.cmake` files do get `path` rows. `_not_indexed_scope` (`cli.py:2646`) compares scanned files against `path`, so it will not name them. A query for a shell function on the published wheel therefore returns empty with no "read the file directly" hint, for exactly the files that need one. I read this from source and did not run a build to confirm it.
- **Test concern:** `tests/test_script_front_end.py` skips the shell and CMake definition tests at lines 179–181, 197 and 226 when the grammar is absent. Under your rules, a capability-conditional skip still hides the feature, so the suite passes on the published wheel without exercising it.

Options for the discrepancy: have `register_paths` skip script types whose grammar is absent, so the miss report names them, or have `_not_indexed_scope` treat a `path` row with no symbols as missing for those suffixes. I'd take the first, since it matches the docstring. I haven't changed anything.