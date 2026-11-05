## Short answer

Clew does not decide inclusion file by file. It resolves one **index scope** before the build starts. That scope is either a declaration in the repo's own `index_scope:` section, or the whole repository minus what git ignores. The resulting roots and excludes are handed to doxygen (or to the parse-built front end for JS/TS and Rust), and whatever survives is what the index holds.

## How the decision is made

```
build starts
  │
  ├─ .clew.yaml has index_scope:?  (clew/scope.py derive_scope)
  │     ├─ yes, usable  → roots = declared dirs that exist; excludes = declared
  │     ├─ yes, but unusable → rejected (unknown key, not a mapping, no roots)
  │     │                     → logged as a WARNING, falls to whole-repo tier
  │     └─ no section   → whole-repo tier
  │
  ├─ Doxyfile: repo's own (ALIASES/PREDEFINED only) or synthesized (empty INPUT)
  │
  └─ doxygen / parse front end walks roots, honouring excludes
```

- **Declared scope is the only tier that is a decision about the index.** `_declared_index_scope` reads `roots:` and `excludes:`. Roots are taken at their word and never walked, so a clone of another repo under a declared root is indexed. A root that does not exist is dropped. Unknown keys reject the whole section (fail closed) rather than being silently ignored.
- **The Doxyfile's `INPUT` no longer decides scope.** This changed in gh#333. The Doxyfile is a documentation target, not a reasoning boundary. A repo that shipped a Doxyfile used to get only its published-API subset, which punished documenting itself. Its `ALIASES` and `PREDEFINED` are still used.

## When nothing is declared

`derive_scope` falls through to `whole_repo_scope`, which is the default tier, not a last resort. Its single root is the repository itself. It subtracts:

1. **Git-ignored paths**, from `git ls-files --ignored --exclude-standard --directory`. Git is invoked through `git_argv`/`git_env` so a target's own `.git/config` cannot run code. The ignore list is also collected inside each nested git tree, because a submodule's `.gitignore` is invisible to the parent.
2. **Dot and cache directories** anywhere in the tree, via `_skip_dir`: any name starting with `.`, plus `__pycache__` and `node_modules`.
3. **Depth cutoff**: the walk stops at depth 16 (`_MAX_DEPTH`). Directories past that are taken wholesale and recorded, so the scope can say where it stopped.

Nested git trees (vendored deps, submodules) are **included**, not excluded. `external.py` tags their rows afterward so two codebases in one index can still be told apart in an answer. The gate's `files:` pattern (doxygen-guard) is deliberately not read. That pattern answers what must be documented, not what should be indexed.

The reason string records that the whole repo was used and why, and it is logged. This matters because a declaration that exists but yields no roots must not be reported as "none declared."

## Build-side consequences with no declaration

- **No Doxyfile:** `synthesize_doxyfile` writes a minimal one with `PROJECT_NAME`, an absolute `OUTPUT_DIRECTORY`, `STRIP_FROM_PATH` set to the repo root, and an empty `INPUT`. The scope then supplies `INPUT`. `STRIP_FROM_PATH` is what keeps stored paths repo-relative; without it, rows held absolute build-machine paths.
- **JS/TS/Rust (parse-built front end):** `_scanned_files` walks `[repo_root]` under the same excludes. The index's own inventory notes that a file whose extension no grammar handles is not indexed at all, so "in scope" and "indexed" are not the same set.
- **Extra excludes:** the operator's `extra_exclude` and the toolchain skips are also applied at this stage, according to the `_scanned_files` docs.

## Things I could not confirm

I did not read the body of the file-extension or grammar filter, or the toolchain skip logic, so I cannot give their exact rules. The `docs/languages/C_INTEGRATION.md` section "The three things that decide what gets indexed" names `INPUT`, `EXCLUDE`/`EXCLUDE_PATTERNS` and `FILE_PATTERNS` as the C-side knobs, but I did not read its full text. This answer reflects the index's records for `clew/scope.py`, `clew/doxygen.py` and `clew/cli.py` as of this target.