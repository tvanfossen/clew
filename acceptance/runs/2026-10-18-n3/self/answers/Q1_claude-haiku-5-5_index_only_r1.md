**Short answer:** the index scope is chosen by a three-tier cascade. A scope passed by a caller wins, then an `index_scope:` block in the repo's `.clew.yaml`, then the whole repository. Within the chosen scope, files are kept only if a grammar handles their extension. With nothing declared, clew indexes the whole repository minus git-ignored paths and dot/cache directories.

**1. Which scope applies (`clew/scope.py`)**

`derive_scope(repo_root, stated)` is the single entry point (`scope.py:639`):

| Tier | Source | What it yields |
|---|---|---|
| 1 | Caller-stated `index_scope` (for example an MCP tool call) | Roots from the stated dict |
| 2 | `index_scope:` in `.clew.yaml` | Roots from `_declared_index_scope` (`scope.py:991`) |
| 3 | Nothing usable | `whole_repo_scope` |

- **Declared roots are taken at their word and never walked.** A root that does not exist on disk is dropped with a warning.
- **Only `roots` and `excludes` are accepted keys** (`_INDEX_SCOPE_KEYS`, `scope.py:406`). An unknown key refuses by name instead of being silently ignored.
- **`roots` is required.** An `excludes`-only block does nothing and counts as rejected.
- **A rejected declaration falls through to tier 3 with a warning.** The build-time guard `declared_scope_rejection` (`scope.py:612`) lets the CLI and MCP refresh refuse instead of silently building the widest scope.
- **The Doxyfile's `INPUT` no longer decides the scope** (gh#333). A Doxyfile still supplies aliases and predefined macros, and `_doxyfile_scope` (`cli.py:2783`) records its `INPUT`, `EXCLUDE_PATTERNS` and `FILE_PATTERNS` only as the repo's own documentation scope, for the provenance record.
- **The doxygen-guard gate does not set index roots.** A test asserts that a gate `files:` pattern alone derives no scope.

**2. What "nothing declared" produces**

`whole_repo_scope` (`scope.py:683`) builds a single root at the repository, with these excludes:
- Paths git ignores, including the ignore rules inside each nested git tree.
- Dot directories and cache directories.

Nested git trees (vendored clones, submodules) are **included**, not cut out. `external.py` tags their rows afterwards so answers can say which codebase a symbol came from. The reason string records that no declaration was found and where clew looked, and it is stored in the build's provenance metadata.

**3. Extension filter within the scope**

Being in scope does not mean being indexed. A file's extension decides which front end parses it:
- Doxygen handles C/C++ and Python, with grammar tables `harvest._CPP_EXTS`, `_PY_EXTS` and `_TS_EXTS`.
- `synth.SYNTH_EXTS` covers JS/TS.
- `SCRIPT_EXTS` covers shell and CMake.

After the build, `_not_indexed_scope` (`cli.py:2646`) compares the files the walk saw with the `path` rows actually written. It stamps `not_indexed` (counts by extension) and `not_indexed_count`. A query miss can therefore be read as "symbol absent", "file type not indexed by this build", or "outside the declared scope".

**Caveat:** I read the scope resolution and provenance code from the index, but I did not read the walker that applies the extension filter. The extension behaviour above comes from the tables and the not-indexed reporter, not from the walk code itself.