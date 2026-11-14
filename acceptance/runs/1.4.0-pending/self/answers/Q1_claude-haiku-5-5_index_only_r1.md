Short answer: the file set is decided in two stages. First, a **scope** decides which paths are walked at all. Then a **file-type filter** drops binaries before anything parses them. With nothing declared, the scope is the whole repository minus what git ignores and the dot and cache directories.

**Stage 1: scope (`clew/scope.py`)**

`derive_scope(repo_root, stated)` (line 639) resolves the scope. It has two tiers:

1. **Declared scope.** `_declared_index_scope` reads an `index_scope:` block from `.clew.yaml`, which takes `roots:` and `excludes:`. Roots are taken at their word and never walked. Excludes are applied during the walk. A stated scope passed in a tool call goes through the same code. The block is validated strictly:
   - An unknown key inside `index_scope` refuses by name instead of being silently ignored.
   - A block that is present but yields no usable root is rejected with a reason. It is not reported as absent.
   - Roots that don't exist on disk are dropped.
   - `excludes` alone does nothing, because `roots` is required.
2. **Whole repository.** `whole_repo_scope` (line 683) is the fallback. It has one root, the repo itself. Its excludes are:
   - paths git ignores, asked per tree, including inside nested git trees such as vendored submodules, since a parent's `git ls-files` cannot see a submodule's own `.gitignore`;
   - dot-directories and cache directories, which no repo restates.

   Its reason string says which case applied, for example "no index_scope is declared for this repo".

Two things the code says explicitly:
- The Doxyfile no longer chooses the input set. Since gh#333 it supplies aliases and predefined macros only. An older Doxyfile-as-scope fallback was removed.
- Nested git trees are not excluded. They are indexed and tagged afterward by `external.py`, so two codebases in one index can still be told apart.

Excludes are enforced during the walk. `_files_under` (`clew/treescan.py:163`) does not descend into excluded directories, so `.git`, `.venv` and build output are never visited.

**Stage 2: file type (`clew/filetypes.py`)**

Files inside the scope then pass through `binary_files`. A file is skipped only if it is classified as binary, from its magic numbers and its first 8 KiB. The extension is not trusted. Each skip is logged at INFO. Nothing else is dropped: empty files and very large generated source files are kept, with no size limit. Requirement REQ-DDB-PIPE-011 covers this.

**What the current repo shows**

The index status for this repo is built from the whole-repo tier:
- Excludes: `.git`, `.claude-plugin`, `.github`.
- Files in scope: 435. Indexed: 397.
- Scope reason: `.clew.yaml` exists but carries no `index_scope`, so the whole repository is the scope.
- 14 files in scope were not indexed, by extension: 3 with no extension, 3 `.csv`, 2 `.rs`, 2 `.toml`, 1 `.jsonl`, 1 `.lock`, 1 `.motor`, 1 `.sql`. The index does not say why each one was left out. Extensions with no parser, such as `.toml` or `.csv`, are a likely cause, but I could not confirm that from the index.

**Caveat:** I answered from the index alone. I did not read `.clew.yaml` or the build log, so the exact contents of the 14 skipped files are unverified.