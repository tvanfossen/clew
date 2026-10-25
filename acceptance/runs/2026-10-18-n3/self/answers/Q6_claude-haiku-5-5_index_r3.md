**Short answer:** For shell and CMake, clew's index holds function definitions, their `#`-block docs and the file's presence. For YAML and JSON it holds only a file-set entry, with no content. Without the bash or cmake grammar, shell and CMake files stay in the file set but get no symbols, and nothing raises. YAML and JSON are unaffected because they never needed a grammar.

I read the code and tests rather than running a build, so the behaviour below is from source, not a live index.

**What the index holds**

| File type | Front end | Rows written | Source |
|---|---|---|---|
| `.sh` `.bash` | `clew/synth.py` + `clew/shast.py` | `memberdef` for `name() {}` and `function name {}`, `dg_source='parse'` | `SCRIPT_EXTS`, `harvest.py` routes to `substrate:bash` |
| `CMakeLists.txt` `.cmake` | same | `memberdef` for `function()`; `macro()` as `kind='macro definition'` | matched by file name as a path component, routes to `substrate:cmake` |
| `.yaml` `.yml` `.json` | `synth.py` | one `path` row each, no symbols | `DATA_EXTS`, "registered and never harvested" |

Shell functions have empty `argsstring` because the language has no parameter list. CMake functions and macros carry their named parameters.

**What it does not hold**

- **YAML/JSON content.** No keys, values or anchors. Writing `block_mapping_pair` or `pair` as symbols was rejected on purpose, since every `steps:` key would land in the function namespace.
- **Markdown**, which goes to the prose corpus instead.
- **Dot directories.** `docs/languages/SCRIPT_INTEGRATION.md` says the scope walk prunes them, so `.github/workflows/*.yml` is out of scope on every tier. I did not verify this in the scope code. This matters for CI, because this repo tracks `.github/workflows/ci.yml` and `release.yml`.
- **Call edges for shell and CMake, unverified.** Shell and CMake are parsed by the shared pass, so the call, lock and thread harvesters could see those trees. The shell and CMake definition harvesters are the only ones I confirmed produce rows for them. Whether the call-site harvester emits anything for bash or cmake node shapes is an open question, and I'd treat it as unknown until tested.

**On an installation whose substrate lacks the grammars**

- `claims()` and `register_paths()` do not check grammar availability. Shell and CMake files still get `path` rows.
- `_ts_language_for()` returns `None` for an absent optional grammar, so the parse and harvest are skipped. The optional keys are `bash` and `cmake` only (`_OPTIONAL_KEYS`).
- No exception is raised. `test_a_missing_grammar_routes_to_nothing_instead_of_raising` pins this.
- A missing `c` or `python` grammar is deliberately not gated. That is treated as a broken install and fails loudly.
- YAML and JSON produce identical output on any install, because they never route through a grammar.

**A doc claim the code does not support**

`SCRIPT_INTEGRATION.md` says the not-indexed report names shell and CMake when their grammars are absent, so a caller is told to read the file. The report in `clew/propose/notindexed.py` is about files outside the index scope and does not consult grammar availability. I found nothing that routes a grammar-less in-scope shell file into it. The doc's claim is either wrong or relies on a path I did not find. The result is that a shell file in scope on a degraded install returns a silent negative. The fix is either to make the report count in-scope files with no grammar, or to correct the doc.

**Two smaller notes**

- The fork's test file says yaml and json are "registered" as substrate keys. `synth.py` never asks for them, so that registration does not affect clew's output.
- The index search for `yaml` returned nothing, which is expected. The `files` corpus holds indexed source only, so data files show up in the file set and the miss report, not in that listing.