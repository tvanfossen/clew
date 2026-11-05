The index holds only a file-set entry for YAML and JSON, and definition rows for shell and CMake. On a substrate without the bash and cmake grammars, those files degrade silently. The documented miss report probably does not name them either, which I could not confirm by running a build.

**What the index holds**

| File type | Path row (file set) | Symbol rows | Notes |
|---|---|---|---|
| `.sh`, `.bash` | Yes | `memberdef` for `name() {}` and `function name {}` | Doc comes from the `#` block directly above. No parameters, since shell args are `$1`/`$@`. |
| `CMakeLists.txt`, `.cmake` | Yes | `memberdef` for `function` and `macro` | A macro is recorded as a macro, not flattened to a function. |
| `.yaml`, `.yml`, `.json` | Yes | None | Registered and findable by name, never harvested. |

- Routing is by extension and, for `CMakeLists.txt`, by whole filename, so `oldCMakeLists.txt` is not claimed (`clew/harvest.py:104-133`, `clew/synth.py:60-83`).
- Markdown is excluded on purpose; prose is chunked by `prose.py`.
- Dot directories are pruned from scope, so `.github/workflows/*.yml` is not indexed at all (`docs/languages/SCRIPT_INTEGRATION.md:89-93`).

**What it does not hold**

- Any YAML or JSON key, shell variable, or CMake `set()` variable. The design rationale is that `steps:` keys would flood the namespace that answers "what does `my_function` do".
- Any symbol for a YAML or JSON file. Those files cannot answer a function question.
- Call-site edges for shell or CMake. The walker docs describe only definitions, and I did not verify whether call edges are produced for them.
- Generic YAML and JSON content only enters the index where clew reads a specific file itself. Examples are requirements, threads, locks, dispatch, data-model and `.clew.yaml` declarations (`clew/requirements.py:367`, `clew/threads.py:448`, `clew/declaration.py:421`, and others). Those are clew's own inputs, not repo files indexed as symbols.

**Installation without the grammars**

The published wheel lacks the bash and cmake grammars (`SCRIPT_INTEGRATION.md:74`). The intended behaviour is:

1. `_ts_language_for` checks `has_language` only for the optional keys `bash` and `cmake` (`clew/harvest.py:137-145`, `:203`). A missing grammar routes to `None` and nothing raises. A test pins this (`tests/test_script_front_end.py:128-141`).
2. The file stays in the file set with no symbols. The harvest skips it (`clew/harvest.py:463`, `:632`).
3. The check is a silent set lookup, so no log line records the absence.
4. The not-indexed report should name `.sh=N` so an empty answer reads as "unread", not "absent".

**Where step 4 likely breaks**

`cli.py:1909` calls `register_synth_paths`, which claims files with `claims()`. That function includes `SCRIPT_EXTS` and `DATA_EXTS` regardless of whether a grammar exists (`clew/synth.py:191-199`, `:83`). So `.sh`, CMake, `.yml` and `.json` get `path` rows even when they have no symbol route.

`_not_indexed_scope` (`clew/cli.py:2673-2684`) counts only scanned files with no `path` row. Those files would therefore not be counted, and the report would not name them.

The fixture (`tests/test_not_indexed_report.py:66-78`) and the doc (`SCRIPT_INTEGRATION.md:81-84`) both assume the opposite. The router test checks only the router, not the production register-then-stamp sequence, so no test catches the gap.

I have not run a build with the bash grammar removed, so this is from reading the code. A build against a substrate without bash would settle it: check whether `.sh` appears in `not_indexed` in the index metadata.

**Suggested fix:** have `_not_indexed_scope` treat a file as indexed only when its extension has a symbol route, or have `register_synth_paths` claim only routed types, then add an end-to-end test on a substrate without bash. Also, the comment at `cli.py:1905` still says the front end is for JS and TS only, which is stale.