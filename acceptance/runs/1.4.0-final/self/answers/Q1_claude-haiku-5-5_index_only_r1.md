**Short answer:** the repository's own `.clew.yaml` decides. If it declares an `index_scope:` with usable roots, those roots are the index. If it declares nothing, the whole repository is the index, minus what git ignores and minus dot and cache directories. A Doxyfile never sets the file set.

**How the decision is made**

`clew/scope.py` resolves scope in two tiers. `derive_scope` (line 639) tries them in order:

1. **Declared (`_declared_index_scope`, line 991).** It reads `index_scope:` from `.clew.yaml`, or from the caller's stated scope when a tool call supplies one. Roots are taken at their word and never walked. A root that does not exist on disk is dropped. Unknown keys inside the section cause a refusal by name, not silent acceptance. A section that is present but yields no roots is rejected with a reason, not treated as absent.
2. **Whole repository (`whole_repo_scope`, line 683).** This is the default and the tier every repo gets when it says nothing. Its one root is the repository root. Its excludes are:
   - everything `git ls-files --ignored --exclude-standard --directory` reports, run per tree including nested git trees;
   - dot-directories and `__pycache__`/`node_modules` anywhere in the tree (`_skip_dir`, `_pruned_dirs`).

**What the Doxyfile does and does not do**

A repo's own Doxyfile still supplies ALIASES and PREDEFINED. Its `INPUT` no longer decides the file set. The module docstring says this was a deliberate reversal (gh#333): honouring the Doxyfile's `INPUT` meant a repo that documented itself got a narrower index than one that did not. The example given is Mbed-TLS, where honouring `INPUT = ../include` indexed 1,571 header declarations and none of the 108 `library/*.c` implementations. The `doxygen-guard` `files:` pattern is also not a scope tier, since it answers what must be documented, not what should be indexed.

**Nested git trees**

Submodules and vendored clones are indexed, not excluded (gh#333/335). `external.py` tags their rows afterward so two codebases can still be told apart in an answer. Only what each nested repo's own `.gitignore` ignores is cut.

**Operator excludes**

`--exclude` adds to the excludes. Its state is recorded in the database's `build_meta`. `_operator_excludes` (`clew/cli.py:918`) reads the previous build's record when the flag is absent, so a refresh does not silently re-widen the index. An empty list withdraws the excludes.

**How the excludes reach doxygen**

Excludes become doxygen `EXCLUDE_PATTERNS`, with absolute directories sent there so doxygen prunes them (`_exclude_lines`, `clew/doxygen.py`). `clew/treescan.py` mirrors the same rules so change detection agrees with what doxygen reads. The walk stops at a depth of 16 and records where it stopped rather than hiding it.

**With nothing declared**

No `index_scope:` means `derive_scope` falls through to `whole_repo_scope`. The build records the reason, so a log line says "no index_scope is declared for this repo" along with the advice to declare one. The index covers the whole tree less git-ignored paths and dot/cache directories, nested trees included. The Doxyfile, if present, is still read for its macros but not for its `INPUT`. A repo that ships no Doxyfile gets a synthesized minimal one, with an empty `INPUT` filled in by the derived scope.

**Caveats**

- I could not confirm from the index which file extensions doxygen keeps. The index shows that a repo's own `FILE_PATTERNS` is respected, but not what the default is for a synthesized Doxyfile.
- `propose_declaration` was denied permission in this session, so I could not check which declaration it would suggest.
- The index marks `doxygen_input_roots` (`clew/treescan.py:349`) as having an anchor mismatch, so its body may differ slightly from the source on disk.