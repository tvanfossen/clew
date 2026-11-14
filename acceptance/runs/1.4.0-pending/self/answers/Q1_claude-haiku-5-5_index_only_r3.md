**Short answer:** the file set is decided by a single declaration, `index_scope:` in the repo's `.clew.yaml`. If none is usable, clew indexes the whole repository minus what git ignores. The Doxyfile does not decide scope any more. Files are then filtered again by whether a grammar handles their extension.

**Decision flow** (from `clew/scope.py`, `derive_scope`):

```
derive_scope(repo_root, stated?)
 ├─ stated by caller?  ─┐
 ├─ .clew.yaml index_scope:  ─┤
 │     ├─ no section ─────────────────────────┐
 │     ├─ section invalid (not a mapping, unknown key,
 │     │   no usable roots) ─► log WARNING with reason ─┤
 │     └─ valid ─► DerivedScope(SOURCE_DECLARED, roots, excludes)
 │                                                      │
 └─ whole_repo_scope(root)  ◄───────────────────────────┘
       roots    = (repo root,)
       excludes = git-ignored paths + pruned dot/cache dirs
```

**The declared tier.** `index_scope:` takes `roots` (required) and `excludes`. Roots are repo-relative. A declared root is taken at its word and never walked, so a foreign clone under it is indexed without being noticed. A root that does not exist on disk is dropped. `excludes` alone does nothing, because `roots` replaces the scope. The loader rejects unknown keys instead of ignoring them, which the code comments call "fail closed". A declaration that is present but unusable is logged with the specific reason, and the build then falls back to whole-repo. The fallback reason says the declaration was rejected, so the log does not claim there was none.

**The undeclared case (the default).** Nothing is declared, so `whole_repo_scope` applies:

- **Root:** the whole repository, including nested git trees (submodules). Those are indexed and tagged by `external.py` so their rows can be told apart in answers. Before gh#333 they were cut out.
- **Excluded:** what git ignores, from `git ls-files --ignored --exclude-standard --directory`. Each nested repo's own ignores are collected separately, because the parent cannot see them through a submodule boundary. Dot-directories and known cache/vendor directories are also pruned. The walk stops at nested trees.
- **Not git:** if the tree is not a repository, or git is missing, nothing is excluded. clew logs a warning and the scope is simply wider.
- **Doxyfile:** if the repo ships one, it still supplies ALIASES and PREDEFINED, but its `INPUT` is ignored. The code treats `INPUT` as a documentation target, not a reasoning boundary. The Mbed-TLS example in the docstring shows the old behaviour indexing only headers and no `library/*.c` files.
- **Gate:** the doxygen-guard `files:` pattern is not consulted. It answers what must be documented, not what should be indexed.
- **Reason string:** the whole-repo result records "no `index_scope` is declared", and advises `propose_declaration`.

**The last filter.** The directory inventory notes that a file whose extension no grammar handles is not indexed at all. So "whole repo" means every file clew has a parser for, not every file on disk. This is the one step I took from the inventory note rather than from a function body I read.

**Caveats:** I read `derive_scope`, `whole_repo_scope`, `_declared_index_scope`, `_gitignored_paths` and `_skip_dir` in full. I did not read `_pruned_dirs` or `_SKIP_DIR_NAMES`, so the exact list of pruned cache directories is unverified. The grammar-extension rule comes from the inventory text, not from a function I inspected.