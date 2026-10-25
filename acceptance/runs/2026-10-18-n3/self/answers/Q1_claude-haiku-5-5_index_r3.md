In clew, the index's file set is decided by a **scope** resolved before doxygen runs. Two inputs matter: a declared `index_scope:` in the repo's `.clew.yaml`, and an extension filter that every build forces. With nothing declared, the whole repository is the scope, minus what git ignores.

**1. Scope resolution (`clew/scope.py`)**

`derive_scope()` is the single entry point. It has two tiers:

- **Declared.** `_declared_index_scope()` reads an `index_scope:` section with `roots:` and `excludes:` keys. Roots are repo-relative. Any other key is rejected, and so is a section with no usable roots. Entries that resolve outside the repo are refused, and entries that don't exist are dropped with a warning. A declared root is taken at its word and never walked.
- **Whole repo.** `whole_repo_scope()` is the fallback and the default since gh#333. Its single root is the repository. Its excludes are:
  - every path `git ls-files --ignored --exclude-standard --directory` reports, including each nested tree's own ignores;
  - dot-directories and `__pycache__`/`node_modules` anywhere in the tree, via `_pruned_dirs()`.

If the declaration is present but rejected, `derive_scope` logs a WARNING and falls back to the whole repo, with the rejection reason carried into the scope's `reason`.

**2. What the Doxyfile does and doesn't do**

A Doxyfile's `INPUT` is no longer a tier. Scope's own docstring says a Doxyfile is "a documentation target, not a reasoning boundary." Its `ALIASES` and `PREDEFINED` are still used. Its `INPUT` is replaced, and the repo's `EXCLUDE` lists are cleared.

**3. Nested git trees**

Nested trees are indexed, not cut out. A directory counts as a separate tree if it holds a `.git` entry (directory or submodule pointer file). Those trees are tagged by `external.py` so the two codebases can be told apart in answers. Separately, `derive_sub_indexes()` splits the repo into a `first-party` index plus one index per nested tree. It does this only when nested trees exist. Otherwise it returns `[]` and the repo keeps its single slug.

**4. The file-type filter**

Which file types get read is a separate decision from scope. `clew/doxygen.py` forces `FILE_PATTERNS` to doxygen's own default list (`DOXYGEN_DEFAULT_FILE_PATTERNS`, lines 203–253) on every build. That includes C/C++, Python, Java, Fortran, VHDL, Markdown and others. A target's declared `FILE_PATTERNS` is read only for reporting. Declaring it does not narrow the index. This was gh#340: a declaration had been vetoing trees that scope had already admitted.

**5. With nothing declared**

For this repo, `.clew.yaml` declares only `guard:` and no `index_scope:`. The build therefore:
- takes the whole repository as one root;
- drops git-ignored paths on both sides of every submodule boundary;
- drops dot and cache directories;
- keeps every nested clone and submodule, tagged as external;
- applies doxygen's default extension list.

It logs a WARNING saying the whole repository is being indexed and why, and says where it looked for a declaration. The reason text also includes the advice to declare `index_scope:`.

**Caveats**

- I read the scope and doxygen-pattern code. I did not run a build to confirm the resulting file list.
- I tried `propose_declaration` to see what clew would suggest for this repo. The call was denied for lack of permission, so I did not use its output.