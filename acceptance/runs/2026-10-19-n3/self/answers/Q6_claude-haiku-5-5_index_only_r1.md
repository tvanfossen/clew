**Short answer:** the index holds shell and CMake files as symbol-bearing files, but it holds YAML and JSON only as registered file types with no content. On an installation whose parser lacks the shell and CMake grammars, those files contribute nothing, and the index says so instead of returning an empty answer that looks like absence.

I answered from the index alone: search results, the repo's own docs and test docstrings, and dossiers of the relevant constants. These are the repository's claims about itself, not behavior I verified by running it.

**What the index holds**

| File type | Extensions / names | Treatment | Holds |
|---|---|---|---|
| Shell | `.sh`, `.bash` | Parsed by clew's own front end (`clew/synth.py`) from the substrate's bash grammar | Functions as `memberdef`-style symbols, so call edges and dossiers work |
| CMake | `.cmake`, plus `CMakeLists.txt` matched by file name | Same as shell, from the substrate's cmake grammar | Functions, same as shell |
| YAML | `.yaml`, `.yml` | Registered in the file set, never harvested | Nothing beyond the file's presence in the claimed set |
| JSON | `.json` | Registered in the file set, never harvested | Nothing beyond the file's presence in the claimed set |

The stated reason for not harvesting YAML and JSON is that their grammars offer only `block_mapping_pair` and `pair` nodes. Writing those as symbols would put every `steps:` key of every config into the symbol table. So the index holds no keys, values, or structure from these files.

**What it does not hold**

- Any YAML or JSON content, including CI workflows, config values, or the structure of configuration.
- Call edges or symbols from YAML or JSON.
- Anything from files that are not in the claimed set. Markdown is prose, and a Doxyfile or other build scripts are outside the file-set corpus.
- Dot-directory YAML by default: the scope note says YAML in `conf/`, `deploy/` or the root is indexed, but CI workflows under `.github/` are not, even though the claim test lists `.github/workflows/ci.yml` as claimed.

**The installation without the grammars**

- The shell and CMake grammars are not in the published `lang-parsing-substrate` wheel. They sit in a fork that is open upstream as a pull request. On the published wheel, shell and CMake files carry no symbols.
- The capability gate `_OPTIONAL_KEYS` (`clew/harvest.py`) is `{"bash", "cmake"}`. A route to one of those grammars is checked before it is taken, so a missing grammar does not raise.
- Nothing raises, and the files are simply symbol-less.
- The not-indexed report (`clew/propose/notindexed.py`, `report_not_indexed`) names the file types that were not read, so an empty answer is not read as proof that a shell function does not exist.
- The index records `substrate_languages` in its identity output so a bug report can show which grammars were present.

**Caveats**

- My search for `cmake` in the files corpus returned nothing. The corpus is documented to hold only what the parser indexed, so that miss does not settle whether this repo's own `CMakeLists.txt` is indexed. I could not confirm it from here.
- I could not read the full text of `docs/languages/SCRIPT_INTEGRATION.md`; I worked from its section headings and search snippets.