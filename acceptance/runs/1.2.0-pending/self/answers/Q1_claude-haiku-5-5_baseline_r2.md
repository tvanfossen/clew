**Short answer:** the index scope is decided by a `.clew.yaml` `index_scope:` section if one is declared and usable. If not, the scope is the whole repository, minus what git ignores and minus dot-directories and a few cache directories. Extension filtering happens later, inside doxygen, and it does not decide which files are in scope.

**Flow**

```
clew index <repo>
  └─ _apply_scope (cli.py:758)            --scope defaults to from-guard (cli.py ~348)
       ├─ declared_scope_rejection()      a present-but-broken index_scope is REFUSED (cli.py:815)
       └─ derive_scope (scope.py:639)
            ├─ index_scope with usable roots?  → DerivedScope(source=clew-declaration)
            ├─ index_scope present but rejected → log WARNING, fall to whole-repo, reason says why
            └─ nothing declared → whole_repo_scope (scope.py:683)
                 roots     = (repo_root,)
                 excludes  = git-ignored paths + dot/cache dirs
       └─ _fold_scope_into_args: roots → extra_input, excludes → extra_exclude (cli.py:739)
  └─ doxygen stage (cli.py:1740)
       enumerate_tree(roots, excludes)    walks roots, pruning excluded subtrees (treescan.py:203)
       _drop_binary_files                 non-text files removed (cli.py:1745, filetypes.py)
       → in_scope set
```

**The declared path.** `_declared_index_scope` (scope.py:991) reads `index_scope:` from `.clew.yaml`. Only two keys are accepted, `roots` and `excludes`. Any other key is rejected. `roots` is required: with `excludes` alone, or with no root that exists on disk, the declaration is rejected rather than quietly widening to the whole repo. Roots that resolve outside the repo are refused.

**What happens when nothing is declared.** This repo's `.clew.yaml` is an example. It has a `guard:` section but no `index_scope:`, so the index uses the whole-repo tier. That tier is the default since gh#333, not a last resort. It:

| Step | Where | Effect |
|---|---|---|
| Ask git for ignored paths | `_gitignored_paths` (scope.py:845) | `git ls-files --ignored --exclude-standard --directory`, run through `git_argv` and `git_env` so the target's own `.git/config` can't execute code |
| Include nested git trees | `nested_repo_roots`, `_nested_trees_recursive` | Submodules and vendored clones are indexed, not cut out. Their own `.gitignore` is applied too |
| Prune dot/cache dirs | `_skip_dir` (scope.py:490); `_SKIP_DIR_NAMES` = `__pycache__`, `node_modules` (scope.py:57) | Any dot-directory is excluded, plus those two names. A depth cap of 16 stops runaway walks, and the trees it stops at are recorded |
| Doxyfile | scope.py:683 docstring | Ignored for INPUT. Its ALIASES and PREDEFINED are still used |
| Doxygen gate | scope.py:683 docstring | Not read. The gate answers what must be documented, not what should be indexed |

If git is missing or the directory is not a repo, the exclusion list is empty and a warning is logged. The index is then wider, and the code says so rather than failing.

**Extension filtering is separate.** `enumerate_tree` deliberately does not filter by extension (treescan.py:203). Hashing everything means any change forces a doxygen re-run. Doxygen itself reads only files matching `FILE_PATTERNS`. Those are forced to doxygen's own default list (doxygen.py:203, forced at :270), so a target's Doxyfile cannot veto a file that scope admitted. The in-scope set is also passed on as `scanned_files`, which lets the JS/TS front end register files doxygen will not read (cli.py:1747).

**Caveats**
- I read `load_declaration_located` only through its docstring, not its body. I did not verify how `.clew.yaml` is located or parsed.
- I did not run a build, so the behaviour above is from reading the code, not from observed output.