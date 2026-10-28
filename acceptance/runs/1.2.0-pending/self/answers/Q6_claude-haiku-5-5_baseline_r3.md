**Short answer:** for YAML and JSON, the index holds only that the file exists: a `path` row, so it is findable by name and in the file set, with no symbols. For shell and CMake, it holds real definitions (`memberdef` rows with `#`-block docs) when the parser has the grammars, and only the file registration when it doesn't. A missing grammar produces no error and no warning. The file is still registered, just empty of symbols, and the empty-answer reply is supposed to tell the caller to read the file. I checked the code paths below; the one thing I did not verify is the not-indexed reply's wording.

**What each file type gets**

| Type | With grammars | Without the shell/CMake grammars |
|---|---|---|
| `.sh` `.bash` | `memberdef` per `function` or `name()` definition, doc from the `#` block directly above | `path` row only |
| `CMakeLists.txt` `.cmake` | `memberdef` per `function()`, plus `kind = 'macro definition'` for `macro()` | `path` row only |
| `.yaml` `.yml` `.json` | `path` row only, in every case | `path` row only |

- **Shell:** `argsstring` is empty because shell functions take `$1` and `$@`, not named parameters.
- **CMake:** named parameters are recorded in `argsstring`. A macro is kept distinct from a function because it pastes its body into the caller's scope.
- **YAML/JSON:** the design is deliberate. Their grammars offer `block_mapping_pair` and `pair`, and emitting those would put every `steps:` key into the namespace that answers `dossier("my_function")`.

**What the index does not hold**

- Any YAML or JSON key, value or structure. Nothing is harvested from those files at all.
- Any symbol from YAML or JSON, so they never answer a function question.
- Markdown is excluded too. It goes to the full-text corpus through `clew/prose.py`.
- JSON gets no file-level documentation. `clew/filedocs.py:272` says so explicitly.
- Dot-directories are pruned from the scope walk (`clew/scope.py:492`). `.github/workflows/*.yml` is therefore not indexed on any tier. YAML under `conf/`, `deploy/` or the root is.
- I did not verify whether shell or CMake definitions feed the call-edge layers. `clew/harvest.py` routes `.sh` through the tree-sitter router, so there may be some call information, but I did not confirm it. Treat call edges for these files as unknown.

**What happens on an installation whose parser lacks the grammars**

1. `register_paths` still writes `path` rows for all `.sh`, `.cmake`, `CMakeLists.txt`, `.yaml` and `.json` files. `claims()` in `clew/synth.py` does not consult grammar availability, so the files stay in the file set.
2. `clew/harvest.py:203` checks `_grammar_available()` only for `bash` and `cmake`, the two keys in `_OPTIONAL_KEYS`. If the key is missing, the router returns `None`, the harvester gets no tree, and no `memberdef` rows are written.
3. Nothing raises. The check exists because the alternative is `ValueError: unknown language key`, which would kill a build partway through a parse pass. The other grammars (C, Python and so on) are not gated: a substrate without them is treated as broken and fails loudly.
4. Availability is decided by asking the installed substrate (`substrate.has_language`), not by comparing version strings, because the fork's wheel reports the same version as the published one.

**Caveats**

- The claim that the grammars are "not in the published substrate wheel" comes from `docs/languages/SCRIPT_INTEGRATION.md`. I did not check the substrate package itself.
- The empty-answer reply naming those file types is what the doc describes. I checked that the reply reads extensions from the file set (`clew/mcp_server/emptiness.py`), which includes these registered rows, but I did not confirm the exact wording.