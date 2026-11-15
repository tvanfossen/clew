The short answer: a declared `index_scope:` decides, and when nothing is declared the whole repository is indexed, minus what git ignores and the dot and cache directories. A Doxyfile no longer decides the file set.

**How the decision is made**

1. **Entry point.** `_apply_scope` in `clew/cli.py:758` runs for the default `--scope from-guard`. It calls `derive_scope_logged`, which calls `derive_scope` (`clew/scope.py:639`). That returns a `DerivedScope` with `roots` (what doxygen gets as INPUT) and `excludes`.
2. **Tier 1: a declared `index_scope:`.** `_declared_index_scope` (`clew/scope.py:991`) reads `index_scope:` from `.clew.yaml`, or from the caller's stated options. Keys are validated against a fixed set, and a declaration with unknown keys is rejected by name. Roots must exist on disk and be non-empty; `excludes:` alone does nothing. Declared roots are taken at their word and never walked.
3. **Rejection is a refusal, not a fallback.** If the declaration is present but unusable, `_apply_scope` calls `declared_scope_rejection` and exits with an error. It does not quietly widen to the whole repo. `derive_scope` on its own would fall back to the whole repo for any other caller.
4. **Tier 2: the whole repository (the default).** `whole_repo_scope` (`clew/scope.py:683`) makes the repo root the single INPUT root. Its excludes are:
   - everything `git ls-files --others --ignored --exclude-standard` reports (`_gitignored_paths`, `scope.py:845`), run with a sanitised git environment, and
   - the same for each nested git tree, since a submodule's own `.gitignore` is invisible to the parent;
   - dot-directories and `__pycache__`/`node_modules` (`_skip_dir`, `_pruned_dirs`, `scope.py:908`). The walk stops at depth 16 and records where it stopped.
   
   Nested git trees are **indexed, not excluded** (gh#333). The walk does not descend into them, but they are tagged afterwards by `external.py`.
5. **Doxyfile.** Its `INPUT` is replaced by the derived roots. The repo's own Doxyfile is still used for ALIASES and PREDEFINED. The module docstring says the Doxyfile's INPUT is "a documentation target, not a reasoning boundary", and the Mbed-TLS example in that docstring shows why it was dropped.

**What happens when nothing is declared**

- No `.clew.yaml`, or no `index_scope:` section: `_declared_index_scope` returns `None` and `derive_scope` returns `whole_repo_scope`. The reason string names the file it looked in and says the whole repository was used.
- A repo that ships no Doxyfile gets the same whole-repo scope. `_declaration_advice` points the owner at `propose_declaration`.
- The consequence is breadth: every untracked-but-not-ignored file under the root is walked, including vendored trees that are not gitignored. The git-ignore list is the only thing that narrows it.
- If the directory is not a git repo, `_gitignored_paths` logs a warning and excludes nothing, so the scope is wider still. The code says so: "a silently wider index is the outcome this project keeps paying for."

**Two things I could not confirm**

- Which file extensions reach doxygen when nothing is declared. The tests suggest the target's own `FILE_PATTERNS` survives, but I did not read the doxygen-invocation path, so treat that as unverified.
- A stale docstring: `_declared_index_scope` (`scope.py:991`) still says a missing declaration "drops the resolution to the Doxyfile's own INPUT". The code no longer does that. It returns `None` and the caller falls through to the whole repo. The docstring contradicts the code, and I'd fix it.