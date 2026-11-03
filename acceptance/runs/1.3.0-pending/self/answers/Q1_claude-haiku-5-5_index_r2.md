When clew indexes a repository, the decision about which files enter the index is made in one place: `derive_scope` in `clew/scope.py:639`. Everything else either feeds it a declaration or consumes its result.

**The decision, in order**

1. **Tier 1, a stated scope.** An MCP or API caller can pass `index_scope` directly. `_declared_index_scope` (`scope.py:991`) reads it in place of any file.
2. **Tier 2, the repo's `.clew.yaml`.** Otherwise it reads the `index_scope:` section via `load_declaration_located` (`declaration.py:299`). Its `roots` replace the scope and `excludes` subtract from it. A root that doesn't exist on disk is dropped, and a declared root is taken at its word and never walked.
3. **Tier 3, the whole repository.** If neither tier yields usable roots, `whole_repo_scope` (`scope.py:683`) returns the repo root as the single root.

There is no third "read the Doxyfile" tier any more (gh#333). A Doxyfile's `INPUT` is a documentation target, not a reasoning boundary, so `cli.py:_fold_scope_into_args` sets `replace_input`. The Doxyfile still supplies `ALIASES` and `PREDEFINED`, but not the file list.

**What gets subtracted in the whole-repo tier**

- Anything git ignores, from `git ls-files --others --ignored --exclude-standard --directory` (`_gitignored_paths`, `scope.py:845`). The command goes through `git_argv` and `git_env`, so a target's own `.git/config` can't run code.
- Nested git trees are indexed, not excluded. Their own ignores are collected separately, since the parent's `ls-files` stops at the submodule boundary.
- Dot-directories and `__pycache__`/`node_modules` (`_skip_dir`, `scope.py:490`), applied as EXCLUDE entries by `_pruned_dirs` (`scope.py:908`). The walk stops at depth 16 and reports where it stopped.

**Which files doxygen actually reads**

The scope gives roots and excludes. Which extensions are parsed is a separate, forced setting. Since gh#340, `FILE_PATTERNS` is always doxygen's own default list (`doxygen.py:203`, `:270`). A declared or Doxyfile `FILE_PATTERNS` is read only for reporting. A repo can't narrow the extension set by declaring it.

**When nothing is declared**

- The whole repo is the root, minus git-ignored paths and dot/cache directories.
- No error is raised. `derive_scope` logs the reason at INFO ("no index_scope is declared for this repo … so the whole repository is the index scope…"), and that reason is stored in `IndexScope` (`clew/query/models.py`).
- If the directory is not a git repo, or git is missing, nothing is subtracted and a warning is logged. The index is wider than the repo asked for, and the code says so.

**Failure modes that look similar but are not the zero-config path**

- A malformed YAML file is logged at WARNING and treated as absent, so the build falls back to whole-repo.
- A file whose `index_scope:` is present but unusable (not a mapping, unknown key, no existing root) is a *rejection*. `derive_scope` logs it and falls back to whole-repo, with the rejection as the stated reason. The log no longer says "nothing declared" when something was declared (gh#5).
- An unknown top-level section name in `.clew.yaml` raises `DeclarationError` and refuses the build, because a misspelled section would otherwise be silently ignored.
- A stated `index_scope` combined with a non-default `--scope` exits 1 (`cli.py:780`). Only the from-guard path reads a stated scope, so anything else would silently build a different boundary.

**Caveats**

- The `index` tool description names `from-declaration` as the default. In the code, `from-declaration` is normalised to `from-guard` (`scope.py:451`), and the default is `from-guard` (`cli.py:348`). The two names mean the same thing.
- I read this from the index's briefs and source bodies, plus the `cli.py` and `doxygen.py` sections directly. I did not run a build on a sample repo, so the behaviour above is what the source says it does, not a measured result.