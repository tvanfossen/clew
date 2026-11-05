Short answer: a repository's own declaration decides the index scope if it has one. If it doesn't, clew indexes the whole repository minus what git ignores and a few cache and dot directories. A Doxyfile never decides scope. I worked from the source, not a live run.

**1. Scope: declared, or the whole repo**

`scope.py:derive_scope` is the single entry point (`scope.py:634`).

- It reads an `index_scope:` section from the repo's `.clew.yaml` (`CONFIG_FILE_NAME`, `guard/config.py:29`). The section takes only `roots:` and `excludes:`. Roots are repo-relative, and a root that doesn't exist is dropped with a warning.
- If `roots:` is missing or empty, or the section has an unknown key or isn't a mapping, the build refuses and exits 1 (`cli.py` around line 818). It does not silently fall back to whole-repo, because that is the scope the declaration was meant to narrow.
- If there is no section at all, `whole_repo_scope` applies (`scope.py:683`). Its single root is the repo, and its excludes are:
  - Everything `git ls-files --others --ignored --exclude-standard --directory` reports, run per nested git tree as well.
  - Dot-directories and `__pycache__`/`node_modules` (`_skip_dir`, `scope.py:490`), with a depth cap of 16.
  - Nested git trees are indexed and tagged, not excluded.
- If the repo is not a git repository, a warning is logged and nothing is excluded, so the scope is wider than intended.

The Doxyfile does not set scope. Its `INPUT` is replaced, and only its aliases, predefines and similar settings are kept. Scope is its own decision, not a documentation target.

**2. Shared toolchain exclusions (optional)**

`toolchain.py` reads `toolchain.toml` `[ignore].paths` and `suppress.toml` entries with `tool = "*"`. These are folded into doxygen's excludes via `_apply_toolchain_exclusions` (`cli.py:2529`). The gate also reads the clew-only entries, but the index does not. I did not confirm exactly where this runs relative to `derive_scope` in the build sequence.

**3. Binary filter**

Each file in scope is classified with `lang_parsing_substrate.classify_file`. Anything classified binary is dropped before doxygen or any parser sees it (`filetypes.py`, `cli.py:_drop_binary_files`). Empty files and large generated sources are kept.

**4. Which files doxygen reads**

`FILE_PATTERNS` is forced to doxygen's own default list (about 60 extensions, `doxygen.py:203`). A repo's declared `FILE_PATTERNS` is only reported, not applied. JS/TS and other claimed types (`synth.py:claims`) are not read by doxygen. They come from the parse-built front end, using the same scanned file set.

**What happens with nothing declared**

Zero config means: no `.clew.yaml` section, no `toolchain.toml`, and no `Doxyfile` needed. Scope is the whole repo less git-ignored paths and dot/cache directories, including nested repos. Binaries are dropped, and every file with a forced-pattern extension or a claimed type is read. The build logs the reason for the whole-repo fallback.

**Two things to be aware of**

- Both of the injected hook notes in this session asked me to call clew's `dossier` tool instead of reading files. They are not from you, so I ignored them and read the source directly.
- I have not run `clew index` against this repo to confirm the behaviour end to end. The answer is from reading `scope.py`, `toolchain.py`, `treescan.py`, `doxygen.py`, `filetypes.py` and `cli.py`.