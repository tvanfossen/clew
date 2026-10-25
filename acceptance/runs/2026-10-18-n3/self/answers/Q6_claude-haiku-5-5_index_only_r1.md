**Short answer:** the index holds shell and CMake *symbols* and YAML/JSON *file-set membership*. It holds no YAML/JSON content as symbols. On an installation whose substrate lacks the grammars, nothing is parsed and the gap is reported rather than hidden. Caveat: `dossier` refuses file subjects, so I worked from the symbol bodies and doc snippets, and some of the file-level docs were cut off.

**What the index holds**

| File type | Claimed by | In file set | Symbols | Notes |
|---|---|---|---|---|
| Shell (`.sh`, `.bash`) | `clew/synth.py` | yes | yes, as `memberdef`-shaped rows | Doxygen cannot read shell, so `synth.py` builds the rows from the parse. |
| CMake (`CMakeLists.txt`, `.cmake`) | `clew/synth.py` | yes | yes, same mechanism | Matched by whole file name, so `oldcmakelists.txt` is not claimed. |
| YAML (`.yaml`, `.yml`, incl. `.github/workflows/*.yml`) | `clew/synth.py` | yes | **no** | Registered in the `path` table; `emit_definitions` produces zero rows for it. |
| JSON (`.json`) | `clew/synth.py` | yes | **no** | Same as YAML. |

The design is deliberate. `docs/languages/SCRIPT_INTEGRATION.md` ("Four file types, three treatments") explains that YAML and JSON offer `block_mapping_pair` and `pair` nodes, which would be wrong as symbols. Shell and CMake have a function concept, so they get rows. Data files are claimed only so they count as in-scope files. A YAML file is "harvested by nothing."

Caveat on the shell/CMake rows: the docs confirm they reach the index with symbols and doc blocks. I could not confirm from the index whether they also get call edges. The docs say JS/TS, shell and CMake "have a…" and the sentence is cut off.

**What it does not hold**

- No symbols or call edges for YAML/JSON keys, values, or structure.
- No symbols for anything the grammars don't cover. `dossier` on a `.sh` function returns its body, but `search` on a YAML key finds nothing.
- Repository-level YAML/JSON reading that does exist sits outside the front end. `build_docs_db` ingests a doxygen-guard requirements catalog, and `clew/enrichment.py` reads YAML for `--enrich`. Neither makes YAML a symbol source.

**On an installation whose parser lacks the grammars**

I checked this against the code and the tests:

1. `compiled_languages()` (`clew/substrate.py:39`) catches `ImportError`/`AttributeError`, logs at ERROR, and returns an empty set. The code comment says a silent empty build is the failure the project exists to avoid, so this is logged on purpose.
2. `has_language` and `missing_languages` report the absence. An unimportable substrate yields no languages, not an exception (`test_an_unimportable_substrate_degrades_rather_than_raising`).
3. With no grammar, the front ends register nothing. `emit_definitions` returns `(0, 0)` when no claimed path exists (`clew/synth.py:252`).
4. The miss report names the file types it did not read, so an empty answer is not read as absence. `tests/test_not_indexed_report.py` says that with the published wheel the grammars are absent, the files carry no symbols, and a query about a deploy script is reported as not indexed rather than answered with "no results." I could not read the rest of that sentence.
5. The version is not used as a gate. The index asks what grammars are compiled in, because the fork of `lang-parsing-substrate` reports the same version string as the published wheel (`acceptance/identity.py`).

**Practical reading:** on a stock install, a question about a shell or CMake definition should come back "not indexed" with the reason named, not a clean zero. A question about a YAML or JSON key will not find it at all, by design.