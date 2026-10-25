**Short answer:** the index holds YAML and JSON files only as file-set entries. It has no symbols, keys, values, or comments from them. Shell and CMake get real definitions, but only when the installed substrate has the bash and cmake grammars. The published substrate wheel lacks them, so on that install shell and CMake also contribute nothing. Two points below are from reading the code, not from running it.

**What the index holds**

| File type | Rows written | Symbols | Source |
|---|---|---|---|
| `.sh` `.bash` | `path` row, plus `memberdef` for functions when the bash grammar is present | Functions only; `#` block above a definition is the doc | `clew/synth.py`, `clew/harvest.py:126` |
| `CMakeLists.txt` `.cmake` | `path` row, plus `memberdef` for `function()` and `macro()` when the cmake grammar is present | Functions and macros (macro recorded as `kind = 'macro definition'`) | `clew/synth.py:62,69`, `docs/languages/SCRIPT_INTEGRATION.md` |
| `.yaml` `.yml` `.json` | `path` row only | None, by design | `clew/synth.py:71-80` |

For YAML and JSON the code says so directly: their grammars offer `block_mapping_pair` and `pair`, and writing those as symbols would put every `steps:` key into the namespace that answers `dossier("my_function")`. The files are "visible": findable by name through `search(corpus='files')`, and named by the not-indexed report when a query comes back empty.

**What it does not hold**

- No keys, values, or nesting from YAML or JSON. `dossier` on a key or a workflow step returns nothing.
- No call edges, `refid`, or `memberdef` rows for any of them.
- No CI workflows under `.github/` (the scope walk prunes dot directories), so `.github/workflows/*.yml` is absent on every tier.
- Markdown is not a path row. It goes to the prose corpus, which is a separate layer.

**What happens on an install whose parser lacks the grammars**

- `clew/substrate.py` asks the installed substrate what is compiled in (`lps.languages()`), not what version it is. The fork and the published wheel both report 0.11.2, so a version check cannot tell them apart. Absence is logged, not raised.
- The harvest router maps `.sh` to `substrate:bash` and `.cmake` to `substrate:cmake`. Both are in `_OPTIONAL_KEYS` (`clew/harvest.py:145`), and `_grammar_available` returns False for them. The files are skipped with no error and no symbols.
- The intended outcome, per `docs/languages/SCRIPT_INTEGRATION.md` and `tests/test_not_indexed_report.py`, is that an empty answer about a deploy script gets a note saying that file type is not indexed here, so the caller reads the file instead of trusting the negative.

**A gap I found while reading**

`register_synth_paths` (`clew/cli.py:1909`) calls `claims()`, which tests only the extension. It has no `has_language` check. So `.sh`, `.cmake`, `.yaml` and `.json` all get `path` rows on any install, including one without the grammars.

`_not_indexed_scope` (`clew/cli.py:2646`) builds the not-indexed list from scanned files that have no `path` row. A file that has a row is therefore never reported as missing. On a published-wheel install, the report should not name shell or CMake, despite what the docs say. I expect it also does not name YAML or JSON, though those are not gated on the grammars anyway.

I haven't run this. To settle it, build an index over a tree with a `.sh` and a `.yaml` against a substrate without the grammars, then query the `path` table and the `not_indexed` stamp. If the report is silent, the docs and `test_not_indexed_report.py`'s docstring are wrong on this point, and the fix is to make `claims()` or the report consult `has_language`.