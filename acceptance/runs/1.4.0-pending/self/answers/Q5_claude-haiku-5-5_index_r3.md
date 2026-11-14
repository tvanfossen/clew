There are three ways to tell clew how to index a repository, and when they disagree the caller wins, then the in-tree file, then clew's defaults.

**The three ways**

1. **A caller-stated option** at call time. This is the `options` mapping on `build_index`, the MCP `index` tool's arguments, or the CLI flags. Keys use the same names as the declaration file. Two ways to state it are `--declare FILE` and the inline `options` mapping. Build mechanics such as `--scope`, `--index-cache` and `--rebuild` are per-run and have no declaration section.
2. **`<repo>/.clew.yaml`**, the repo's standing declaration. Each section holds exactly what the matching standalone manifest would, so an existing file can be moved in verbatim. Sections include `index_scope`, `shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `preprocessor`, `kconfig`, `doxyfile`, `requirements`, `locks`, `vendored`, `sub_indexes` and others. The `guard:` section is the gate's config and is dropped by the index loader.
3. **The Doxyfile**, which is not a scope setting. Clew still uses it for `ALIASES` and `PREDEFINED`, but its `INPUT`, `EXCLUDE*` and `FILE_PATTERNS` are replaced. Scope is decided only by `index_scope` or by the whole repository, so a Doxyfile that documents a small subset no longer narrows the index.

**When they disagree**

- **Caller vs `.clew.yaml`:** the caller wins. The file is the standing statement and the argument is a one-off override. Build logs name the source, for example "stated by the caller (tier 1)".
- **Requirements catalog:** the order is caller flag, then the declared `requirements:` path, then the gate's `impact.requirements.file`, then the conventional `requirements.yaml`, then nothing. The declared path inserts one tier above the gate's declaration and does not replace the resolver.
- **Empty values:** `requirements: ""` or `[]` is a deliberate withdrawal and does not fall through to the file. An empty inline mapping does fall through to the declaration.
- **`index_scope` vs a stated `--scope`:** a caller-supplied `index_scope` combined with any `--scope` other than `from-guard` is refused, because that path never reads it.
- **A declared `index_scope` with no usable roots:** this falls back to the whole repository and logs a warning that names the rejection. It does not silently guess.
- **Doxyfile vs anything:** the Doxyfile never decides scope, so no conflict arises. A stated `doxyfile` path must exist, or the build is refused rather than falling back silently.
- **Refresh:** a plain refresh inherits options from the earlier build. Passing an option again replaces it.

**Errors versus defaults**

- An unknown top-level section name is refused by name, so a misspelled section fails the build instead of quietly running on defaults. The exception is a key prefixed `x-`, which is tolerated with a warning.
- Malformed YAML, or a file that is not a mapping, is logged at WARNING and treated as absent, so the build falls back to defaults.
- A file containing only comments states nothing and is logged at INFO. `propose_declaration` relies on this to draft a file that changes nothing until uncommented.

Sources: `clew/declaration.py`, `clew/buildoptions.py`, `clew/cli.py` (`_declared_or_flag`, `build_index`), `clew/scope.py` (`derive_scope`), and `docs/languages/C_INTEGRATION.md`. I did not run a build to confirm these paths at runtime; the answer is from the source and docstrings.