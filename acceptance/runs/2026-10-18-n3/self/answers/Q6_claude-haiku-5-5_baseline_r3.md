**Short answer:** for YAML and JSON the index holds only a file-name row. For shell and CMake it holds function and macro definitions, but only when the installed substrate has the bash and cmake grammars. On a substrate without those grammars, the code does not do what the docs say: the not-indexed report stays silent about `.sh` and `.cmake` files. I read the code and did not run a build, so that last point is from reading, not from a run.

**What the index holds, by file type**

| File type | Front end | What lands in the index |
|---|---|---|
| `.sh` `.bash` | `clew/shast.py`, via `clew/synth.py` | `path` row, plus a `memberdef` function row for `name() {…}` and `function name {…}`. Doc text comes from the `#` block directly above. No parameters, since `$1` is not a declared parameter. |
| `CMakeLists.txt` (by whole name) `.cmake` | `clew/cmakeast.py`, via `clew/synth.py` | `path` row, plus a `memberdef` row for each `function()` (with its named parameters) and each `macro()`, which is stored as kind `macro definition`. |
| `.yaml` `.yml` `.json` | none | `path` row only. `synth.py` says this on purpose: YAML and JSON have no function concept, so writing their keys as symbols would bury real functions. |

Markdown is handled separately by `clew/prose.py` and is searchable through `search(corpus='prose')`.

**What it does not hold**

- No call edges, threads, locks or other richness layers for shell or CMake. The harvesters emit definitions only.
- No file body or key-level content for YAML or JSON. Nothing in them is queryable beyond the file name.
- YAML and JSON are never parsed. `harvest.py`'s `_TS_GRAMMARS` table has no YAML or JSON entry, so neither grammar is consulted. `clew/substrate.py`'s docstring lists them as one of the fork's five grammars, but clew does not use them.
- Dot directories are pruned from the scope walk (`docs/languages/SCRIPT_INTEGRATION.md`). `.github/workflows/*.yml` is neither indexed nor reported as missing. The YAML in `conf/`, `deploy/` or at the root is indexed.
- `.clew.yaml` is read as configuration by the index and the gate (`guardconfig.py`, `locks.py`, `shared_key_edges.py`, and others). Its contents do not become rows.

**An install without the grammars (published wheel)**

What the code does:
- `harvest.py`'s `_ts_language_for` returns None for `.sh` and `.cmake` when the optional grammar is absent, so the file is skipped without raising. Nothing crashes.
- `synth.register_paths` still writes `path` rows for `.sh`, `.bash`, `.cmake`, `CMakeLists.txt`, `.yaml`, `.yml` and `.json`. It checks `claims()` only, never `has_language()`.
- `cli._not_indexed_scope` counts scanned files that have no `path` row. Those `.sh` and `.cmake` files do have rows, so they are not counted as missing.
- `query/corpus.indexed_extensions` reads the same `path` rows. `.sh` and `.yaml` therefore look indexed, even though they carry no symbols.

What the docs and tests say:
- `docs/languages/SCRIPT_INTEGRATION.md` says the not-indexed report "names those file types" in that case.
- `substrate.py`'s docstring says the same.
- `tests/test_script_front_end.py` pins the missing-grammar routing (`_ts_language_for` returns None) but does not check the build-level report.

So a caller asking about a deploy script gets an empty answer, and the report that should say "read the file directly" says nothing. This is a real defect. The fix is to have `register_paths` (or its callers) skip the optional-grammar claims when `has_language` is False, or to have `_not_indexed_scope` treat them as missing. Either way, add an end-to-end test that patches `substrate.has_language` to False for `bash`, builds a small repo with a `.sh` file, and asserts that `not_indexed` names `.sh`.

I did not run the test suite or a build here. Confirming the defect would take a build with the published substrate, which needs a venv I did not find in this checkout.