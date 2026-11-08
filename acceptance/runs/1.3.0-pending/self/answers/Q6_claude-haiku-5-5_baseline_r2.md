**Short answer:** the index holds shell and CMake function and macro definitions as symbols, and holds YAML and JSON only as file-set entries. On an install without the bash or cmake grammars, clew does not crash, but the "not indexed" disclosure that the docs promise does not happen. The code registers those files as if they were indexed, so the miss report stays silent.

## What the index holds

| File type | Rows written | Source |
|---|---|---|
| `.sh`, `.bash` | `memberdef` function for `name() {}` and `function name {}`. Brief comes from the `#` block directly above, with no blank line and not counting a shebang. `argsstring` is empty because shell has no parameter list. | `clew/shast.py`, via `_ScriptSymbolHarvester` in `clew/synth.py` |
| `CMakeLists.txt`, `.cmake` | `function` → `memberdef` function with named params in `argsstring`. `macro` → `memberdef` with `kind = 'macro definition'`, so the variable-leak semantics are kept. Same `#`-block doc rule. | `clew/cmakeast.py` (`_DEFINITIONS`, `harvest_definitions`) |
| `.yaml`, `.yml`, `.json` | One `path` row (`type=1`, `found=1`). No symbols, no doc, no body. Findable by name only. | `synth.py` `DATA_EXTS` and `register_paths()` |

Rows are stamped `dg_source='parse'`.

## What it does not hold

- **CMake targets and commands.** `add_executable`, `target_link_libraries` and similar are not rows. Only `function` and `macro` definitions are harvested, so "what this builds" is not queryable structure.
- **YAML and JSON content.** Keys are deliberately not symbols, to keep `steps:` and similar out of the namespace. YAML is still parsed by config loaders for other purposes: `requirements.yaml` feeds the requirements layer, `.clew.yaml` is read as a declaration, and UDM manifests go through `datamodel.py`. None of that makes the YAML searchable as code.
- **Anything under dot directories.** The scope walk prunes them, so `.github/workflows/*.yml` is not in the file set at all.
- **Shell call edges.** I did not trace whether shell calls between functions produce edges. Treat that as unverified.

In this repo specifically, `git ls-files` shows no tracked `.sh`, `.cmake` or `CMakeLists.txt` files. The YAML and JSON files are the only ones in scope, and most JSON is under `acceptance/` and `clew/mcp_server/descriptions/`.

## What happens without the grammars

I checked the code path rather than running a degraded install. The installed venv substrate has every key, including `bash`, `cmake`, `yaml` and `json`, so I could not observe the degraded case directly.

1. `register_paths()` runs in the build before the parse (`clew/cli.py:1909`). It calls `claims()`, which matches by extension only. It never asks the substrate whether it can parse the file.
2. The `.sh`, `.cmake` and `CMakeLists.txt` files therefore get `path` rows regardless of the grammar.
3. `_ts_language_for()` returns `None` for a missing optional grammar (`clew/harvest.py:203`), so no tree is parsed and no symbols are written. There is no exception, and `tests/test_script_front_end.py` pins that.
4. `_not_indexed_scope()` (`clew/cli.py:2646`) reports files in the scanned set that have no `path` row. Because step 2 gave these files rows, they are never counted as missing. The report names nothing for them.
5. `substrate.missing_languages()` is the function meant to produce that disclosure. Its only callers are tests, so nothing in production uses it.

That contradicts the docs. `docs/languages/SCRIPT_INTEGRATION.md`, the `clew/substrate.py` header, and the `synth.py` docstring all say the miss report names these types. The same contradiction applies to YAML and JSON: their `path` rows always exist, so they can never be reported as missing either.

**Practical effect:** a query for a shell function on a degraded install returns nothing, and the answer does not say the file type was skipped. The only remaining signal is the emptiness grader in `clew/mcp_server/emptiness.py`, which decides by extension. Since `.sh` appears in the indexed file set, the grader is likely to treat the empty result as a definitive absence. I did not trace that end to end, so this is the likely outcome, not a confirmed one.

## Suggested fix

Make `register_paths()` consult `substrate.has_language()` for the shell and CMake types, so they are left out of the file set when their grammar is absent. Then the existing `_not_indexed_scope()` will name them without other changes. Decide separately whether YAML and JSON should be reported as "not indexed" at all, since their file-set registration is intentional. Then fix the docs to match whichever behaviour you choose, and add a test that runs the real `_not_indexed_scope()` with a stubbed substrate.