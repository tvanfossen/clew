## Short answer

For shell and CMake, the index holds function-level rows only when the substrate has the grammars. For YAML and JSON it holds a file-set entry and nothing else, on any install. On a published-wheel install, the not-indexed report also fails to name shell and CMake files, which the code's own docs say it does. I traced that statically and did not run a build, so treat it as a strong finding to confirm.

## What the index holds

| File type | Route | Rows written |
|---|---|---|
| `.sh`, `.bash` | `harvest.py:126` → `substrate:bash` | `path` row, plus one `memberdef` (kind `function`) per `name() {}` or `function name {}` (`shast.py:98-140`). Args are empty, and the doc is the `#` block directly above. |
| `.cmake`, `CMakeLists.txt` (matched by whole name) | `harvest.py:127,133` → `substrate:cmake` | `path` row, plus `memberdef` for `function` and `macro` definitions. Macros map to doxygen's `macro definition`. |
| `.yaml`, `.yml`, `.json` | Never routed. `_TS_GRAMMARS` has no entry (`harvest.py:118-127`). | `path` row only (`synth.py:80`, `register_paths`). No symbols, no call edges. |

What it does not hold:

- **Shell:** variables, `source` graph, and command invocations as rows. Generic call-edge code can parse `.sh` with the bash grammar, but I did not verify what it emits.
- **CMake:** `add_executable`, `target_link_libraries`, `set()` variables, `option()`, and `include()` are not rows. The harvester records only function and macro definitions.
- **YAML and JSON:** their content. `synth.py:23-26` says so deliberately. Clew's own config readers (`.clew.yaml`, `requirements.yaml`, the datamodel) parse them outside the index.

Doxygen covers none of these four types. None of its default `FILE_PATTERNS` (`doxygen.py:203` onward) list them.

## What happens without the grammars

1. **No crash.** `_grammar_available` (`harvest.py:213-225`) checks only `bash` and `cmake`, the keys in `_OPTIONAL_KEYS`. When one is missing, `_ts_language_for` returns None. The file is never parsed and gets no memberdef rows.
2. **The path row is still written.** `claims()` (`synth.py:191-199`) and `register_paths` (`synth.py:219-240`) never ask whether the grammar exists. Shell and CMake files therefore enter the `path` table with zero symbols.
3. **The not-indexed report stays silent for them.** `_not_indexed_scope` (`cli.py:2646-2672`) subtracts every `path WHERE type = 1` row from the scanned set. `register_synth_paths` runs at `cli.py:1909`, before that report at `cli.py:2263`. So `.sh` and `.cmake` never appear as missing.
4. **YAML and JSON behave the same on both installs.** They are always path-only and always absent from the not-indexed report, because they always have a path row.

That contradicts the docs. `substrate.py:13-14` says the miss report names these types on the published wheel. `synth.py:6-7` says the data files are "named by the not-indexed report." The unit test `tests/test_not_indexed_report.py:38-44` builds a hand-made `path` table, so it never runs `register_paths` and misses the interaction.

## Also noticed

`missing_languages` (`substrate.py:72`) has no production caller. Only tests use it.

I can fix the mismatch in one of two ways. Either `claims()` skips shell and CMake when their grammar is absent, or the not-indexed subtraction excludes path rows that have no harvest. The second is more honest for YAML and JSON as well. Tell me which you want and I'll make the change with a test that runs `register_paths` and `_not_indexed_scope` together.