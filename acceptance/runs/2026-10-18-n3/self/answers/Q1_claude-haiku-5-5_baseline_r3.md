**Short answer:** two independent gates decide what gets indexed. The first decides which *trees* are walked. The second decides which *files* are read. Nothing in the first gate filters by extension. With no declaration, the walk starts at the whole repository and only subtracts what git ignores plus a few directory rules.

```
repo
 │
 ├─ 1. SCOPE  (clew/scope.py: derive_scope)
 │     index_scope in .clew.yaml?  ── yes ──► declared roots, minus excludes
 │            │ no (or unusable)
 │            ▼
 │     whole-repo: root = repo, minus git-ignored paths, dot-dirs,
 │                  __pycache__, node_modules; nested git trees kept
 │
 ├─ 2. ENUMERATE + BINARY DROP  (treescan.enumerate_tree, filetypes.binary_file)
 │     every regular file under the roots, no extension filter
 │     files that classify as binary → removed, added to doxygen EXCLUDE
 │
 ├─ 3. DOXYGEN  (doxygen.py: forced FILE_PATTERNS)
 │     reads only files matching doxygen's default extension list
 │
 └─ 4. FRONT END  (synth.claims)
       JS/TS/shell/CMake/YAML etc. that doxygen cannot read, registered from the scanned tree
```

**Step 1: scope.** `derive_scope` reads `index_scope:` (`roots`, `excludes`) from the repo's `.clew.yaml`. Declared roots are taken as written and never walked. A declaration is rejected, with a logged reason, if it has unknown keys, has no usable `roots:`, or names roots that don't exist. A rejected declaration falls through to the whole-repo tier.

**What "nothing declared" produces.** `whole_repo_scope` in `clew/scope.py` returns one root, the repository itself, with these excludes:

- Everything `git ls-files --others --ignored --exclude-standard` reports. Nested submodules get their own `.gitignore` queried too.
- Dot-directories (`.git`, `.venv`, `.github`, …) and `__pycache__` / `node_modules`.
- Nothing else. Nested git trees are not excluded. They are indexed and tagged later by `external.py`.

Two details matter here:
- The walk stops descending at depth 16. Those directories are logged and recorded, not pruned, so files below them stay in scope.
- A `Doxyfile` is no longer a scope source. Since gh#333 its `INPUT` is ignored, so a repo that ships one gets the same scope as one that doesn't. Its `ALIASES` and `PREDEFINED` still apply.

If git is absent or the tree is not a repo, the warning says so and nothing is ignored. The result is a wider scope, not a failure.

**Step 2: enumeration and binaries.** `enumerate_tree` deliberately has no extension filter. The content hash for the incremental cache covers every file in scope. `_drop_binary_files` then runs `lang_parsing_substrate.classify_file` on each file. Anything classified as binary is skipped and logged at INFO. Empty files and very large text files are kept.

**Step 3: doxygen.** This is where extension matters. `FILE_PATTERNS` is forced to doxygen's own default list (`DOXYGEN_DEFAULT_FILE_PATTERNS` in `clew/doxygen.py`, covering C/C++, Python, Java, C#, Fortran, Markdown, and others). The target's `FILE_PATTERNS` is no longer honoured. That was gh#340: a declared pattern list could drop a tree that scope had already admitted.

**Step 4: the front end.** Languages doxygen can't read (JS/TS, shell, CMake, YAML and others in `synth.CLAIMED_EXTS`) are registered from the scanned tree after doxygen runs. Claimed files are in the file set even when they produce no symbols.

**Consequences of the default, from reading the code:**
- A file under a dot-directory, such as `.github/workflows/*.yml`, is not in the whole-repo scope at all. Dot-directories are excluded by rule, not by git.
- Declaring `index_scope:` replaces the whole-repo tier entirely. A declared root is taken at its word, so a clone under it is indexed with no check.
- The gh#3 guard flags an `--extra-input` root only when it holds files and none match the patterns. Under the forced default list this almost never fires.

I read the code paths but did not run an index build against this repo, so the behaviour above is from source, not from observed output.