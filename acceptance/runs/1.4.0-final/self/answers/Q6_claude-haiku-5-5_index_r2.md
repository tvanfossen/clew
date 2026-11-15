The short answer: the index holds definitions for shell and CMake, only file-level presence for YAML and JSON, and nothing about their contents. On an install without the grammars, shell and CMake degrade without an error, but the miss report does not flag them, which contradicts its own design docs. I read this from the code and the index's dossiers; I did not run a published-wheel build.

**What the index holds**

| File type | `path` row | Definitions (`memberdef`) | Source |
|---|---|---|---|
| `.sh`, `.bash` | yes | functions, both `name() {}` and `function name {}`, with line spans and the `#` block above as brief | `clew/shast.py`, via `clew/synth.py` |
| `CMakeLists.txt`, `.cmake` | yes | `function` and `macro` definitions; `macro` is mapped to doxygen's "macro definition" | `clew/cmakeast.py` |
| `.yaml`, `.yml`, `.json` | yes | none, by design | `clew/synth.py:71-80` |

- **Shell:** the function's `args` are always empty, since bash has no parameter list.
- **CMake:** named parameters are kept for `function`; `macro` is recorded as distinct because it leaks variables into the caller's scope.
- **YAML and JSON:** they are in the file set so they can be found by name and named in the miss report. Their keys are never symbols, so a `steps:` key does not pollute the function namespace.
- **Markdown** is deliberately left out of the file set; prose goes to the FTS index.

**What it does not hold**

- **No call, thread or lock edges for shell or CMake.** `clew/call_edges.py`, `threads.py` and `locks.py` have no bash or cmake branch. A deploy script that calls another script produces no call edge. Some generic per-file harvesters do receive the bash tree, so I have not ruled out stray rows from them.
- **No classes, variables, `set()` values, target flags, or dependencies.** So "how is this target built" still needs a read of `CMakeLists.txt`.
- **No searchable content for YAML or JSON.** They are findable by path only. I did not test whether the search layer matches their text; the design docs say they are findable by name only.

**What happens on an install whose parser lacks the grammars**

The fork's `bash` and `cmake` keys are gated; `yaml` and `json` are never routed to any grammar, so their absence changes nothing.

1. **Shell and CMake, harvest:** `clew/harvest.py:203` returns no grammar when `_grammar_available` is false. The file gets no tree, no payload, and no `memberdef` rows. This is a silent, no-exception degrade, and `tests/test_script_front_end.py:136` pins it.
2. **Shell and CMake, file set:** `claims()` (`clew/synth.py:191`) is extension-only, and its only callee is `PurePosixPath`. `register_paths` runs unconditionally (`clew/cli.py:1909`). So a `.sh` file still gets a `path` row.
3. **Miss report:** `_not_indexed_scope` (`clew/cli.py:2676`) counts a file as missing only when it has no `path` row. Because of step 2, a `.sh` file is never reported as not indexed.

The result: on the published wheel, a question about a deploy script returns empty, and the index does not say the file type was skipped. That is the exact failure the not-indexed report was built to prevent.

This contradicts the docs. `clew/substrate.py`'s module doc says the front ends "register nothing" and the miss report "names those file types as not indexed." `tests/test_not_indexed_report.py` says the same. Neither holds for path registration.

**Test coverage gap**

- The two end-to-end shell and CMake tests in `tests/test_script_front_end.py` (around lines 179 and 197) skip when the grammars are missing. The project's own rules forbid skips, though this one is conditional on the environment.
- No test runs the absent-grammar case end to end and asserts that the miss report names `.sh`.

**Suggested fix (not applied)**

Gate `claims()` or `register_paths` on `has_language` for `bash` and `cmake`, so an absent grammar produces no `path` row and the miss report names the type. Add a test that monkeypatches `has_language` to false and asserts `not_indexed` contains `.sh`. Tell me if you want me to make that change.