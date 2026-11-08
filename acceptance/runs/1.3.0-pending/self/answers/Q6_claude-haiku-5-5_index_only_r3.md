**Short answer:** for YAML and JSON, the index holds only that the files exist, plus a name the miss report can point to. It holds no symbols and no content. Shell and CMake do get symbols. On an installation whose parser lacks the grammars, nothing crashes: the files are reported as not indexed.

**What the index holds for each type**

| File type | In the index? | Symbols? | Source of this claim |
|---|---|---|---|
| `.sh`, `.bash` | Yes | Yes. Functions become `memberdef` rows, with docs taken from the `#` block above them | `tests/test_script_front_end.py` |
| `CMakeLists.txt`, `.cmake` | Yes | Yes. `function`/`macro` definitions become rows, with macros recorded as macros | same |
| `.yaml`, `.yml`, `.json` | Yes, as a `path` row | No. Keys such as `steps:` are deliberately not symbols | `clew/synth.py`, `tests/test_script_front_end.py` |

The reason for the YAML/JSON exception is in the docs. Their grammars expose `block_mapping_pair` and `pair`. Treating those as symbols would put every config key into the namespace that answers `dossier("my_function")`, which would bury real functions. So these files are findable by name and nothing more.

**What the index does not hold**

- No YAML or JSON keys, values, or structure as queryable rows.
- No call edges or dataflow from these files.
- No symbols at all for YAML or JSON.
- The CMake and shell walkers are their own modules (`clew/cmakeast.py`, `clew/shast.py`). I did not check their coverage, so I cannot say how much of a large script's logic becomes a row.

One separate path reads YAML as data: the requirements catalog (`requirements.format: yaml` in `docs/GUARD.md`). That is a documented input, not part of the general file-type indexing, and I did not check it further.

**On an installation whose parser lacks the grammars**

- `clew/substrate.py` asks the installed `lang_parsing_substrate` what is compiled in. The version string cannot answer this, because the fork that adds these grammars reports the same version as the published wheel.
- If the grammars are absent, `compiled_languages()` returns the empty set. It logs an error, and the front ends register nothing for those types.
- The router checks for a grammar before parsing. A missing grammar routes to nothing instead of raising, so a build does not fail partway through.
- Queries that come back empty then pass through the not-indexed report. It was built to tell a caller three cases apart:
  - the symbol does not exist;
  - the file type is not indexed by this build, so read the file directly;
  - the file type is outside the declared scope.
  The report counts in-scope files of a type that has no rows. Its example is "14 `.sh` files were in scope and none of them are in this index."
- The report is measured at build time, not at query time. An index built before this release reports nothing rather than a fabricated empty set.

**Caveat:** I can't see from the index which wheel this particular index was built against. The index is current (`stale: false`, build version 9), so the behaviour above applies to whichever grammars that build has. To confirm, check whether `compiled_languages()` includes `bash`, `cmake`, `yaml` and `json` on the installation in question.