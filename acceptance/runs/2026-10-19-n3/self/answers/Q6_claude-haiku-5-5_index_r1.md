**Short answer:** the index holds file membership for YAML and JSON, and function-level definitions for shell and CMake. It holds nothing about what is inside the YAML or JSON. On an install whose parser lacks the shell or CMake grammar, those files drop to membership-only, but the not-indexed report may not say so. I worked from the index and source reading, not from running a build.

**What the index holds, by file type**

| Files | Path row (file set) | Symbols | Grammar |
|---|---|---|---|
| `.sh`, `.bash`, `.cmake`, `CMakeLists.txt` | Yes | Yes: function-level `memberdef` rows, with doc blocks reaching the row | `substrate:bash`, `substrate:cmake` via `_TS_GRAMMARS` / `_NAME_GRAMMARS` |
| `.yaml`, `.yml`, `.json` | Yes | None | None |
| `.js`, `.ts`, etc. | Yes | Yes | Parse-built front end |
| `.md` | No | No | Not claimed |

- The shell and CMake handling lives in `clew/synth.py`. `SCRIPT_EXTS` is `.sh/.bash/.cmake` and `CLAIMED_EXTS` is the union of the JS/TS, script and data lists. `emit_definitions` runs the script harvester alongside the JS one.
- `claims()` is documented as "a YAML file is claimed so that it is in the file set, and harvested by nothing." The test `test_the_data_files_are_in_the_file_set_with_no_symbols` asserts that `_members` is empty after YAML and JSON are registered.
- The config corpus holds only preprocessor gate macros (`WIDGET_LOG_LEVEL` and similar). It does not hold YAML or JSON keys, so a search for a config key finds nothing.

**What it does not hold**

- Keys, values, or structure of YAML and JSON. A GitHub workflow such as `.github/workflows/ci.yml` is in the file set, but no job, step or script inside it is indexed.
- Anything doxygen would have produced for these types. Doxygen reads none of the four, so there are no `path` rows from doxygen, no call edges, and no doc-comment structure beyond what the synth walkers emit.
- Cross-file links. A shell script that calls a C binary, or a CMake target, has no edge to anything. I did not verify whether shell or CMake definitions carry call edges at all.
- Markdown, by design. The test asserts `README.md` is not claimed.

**What happens on an install whose parser lacks the grammars**

- Bash and CMake are the only optional keys. `_OPTIONAL_KEYS = {"bash", "cmake"}`. `_grammar_available` checks them, and `_ts_language_for` returns `None` when the grammar is missing. `test_a_missing_grammar_routes_to_nothing_instead_of_raising` pins that outcome. The C, C++, Python, Rust and JS/TS grammars are not optional, so a wheel missing them fails loudly on purpose.
- YAML and JSON have no grammar, so the install's grammar set does not affect them. They are always membership-only.
- If the substrate cannot be imported at all, `compiled_languages()` logs an error and returns an empty set. The optional-key check would then exclude bash and CMake. I did not trace what happens to the non-optional grammars in that case.

**The gap I would check first**

The not-indexed report (`_not_indexed_scope` in `clew/cli.py`) decides what is missing by looking for `path` rows of type 1. `register_paths` calls `claims()`, and `claims()` tests the extension only. It never asks whether a grammar is available. So on an install without the bash grammar, a `.sh` file still gets a path row, is counted as indexed, and does not appear in `not_indexed`. Its symbols are silently absent. This is inferred from the code, not from a test. I did not find a test that covers it, and I could not find the callers of `missing_languages` to confirm whether a missing-grammar warning is ever emitted.

**Smaller items**

- The `_ts_language_for` docstring says it selects "C, C++, Python or Rust". The routing table also covers JS, TS, shell and CMake, so the docstring is stale.
- The index flagged `test_a_missing_grammar_routes_to_nothing_instead_of_raising` as having an anchor mismatch, so the file changed after indexing. Its assertions may differ from what the index shows; I did not re-read it.