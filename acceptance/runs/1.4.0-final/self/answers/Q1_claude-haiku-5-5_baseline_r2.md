The short answer: a file gets into the index only if it survives four filters in sequence. Which scope applies depends on whether the repo declared one. With nothing declared, clew indexes the whole repository minus what git ignores and minus dot and cache directories. I read the code but did not run a build, so the claims below are from source.

```
 declared scope (stated tool arg > .clew.yaml index_scope:)   ← else whole-repo tier
          │
          ▼
 + excludes: toolchain.toml `ignore`, suppress.toml (tool="*"), operator --exclude
          │
          ▼
 enumerate_tree: walk roots, prune excluded subtrees, no extension filter
          │
          ▼
 binary filter: classify_file on first 8 KiB → binary files dropped (INFO log)
          │
          ▼
 doxygen pass: RECURSIVE=YES, FILE_PATTERNS forced to doxygen default set
               (JS/TS come through the parse front end instead)
```

**1. Choosing the root scope (`clew/scope.py`, `derive_scope`)**

- A scope passed directly by a tool call wins. Otherwise `_declared_index_scope` reads `index_scope:` from the repo's `.clew.yaml`. Its accepted keys are `roots` and `excludes`.
- `roots` is required. `excludes` alone does nothing. Roots that don't exist on disk are dropped. Unknown keys reject the whole section.
- A rejected section logs a WARNING, and the build falls back to the whole-repo tier with the rejection stated as the reason. An absent section falls back silently with a reason saying none was declared.

**2. Adding excludes**

- `toolchain.toml` `[ignore] paths` globs, and `suppress.toml` entries with `tool = "*"`, are expanded and appended to the build's exclude list (`clew/cli.py`, toolchain fold-in; `clew/toolchain.py`, `load_toolchain_config`). Entries with `tool = "clew"` only affect the gate.
- `--exclude` is recorded as `operator_excludes` and replayed on later builds.

**3. Enumeration (`clew/treescan.py`)**

`enumerate_tree` walks each root and prunes excluded directories during the walk. It is deliberately not filtered by extension, so the content hash cache also covers files doxygen will never read.

**4. Binary skip (`clew/filetypes.py`)**

Files classified as binary are dropped by content, not extension. Each skip is logged at INFO. Empty files and large text files are kept.

**5. Doxygen's file-type filter (`clew/doxygen.py`)**

clew forces `RECURSIVE = YES` and sets `FILE_PATTERNS` to doxygen's own default set (C, C++, Java and similar), overriding any target Doxyfile. A target's own `EXCLUDE` lists are cleared. So doxygen reads only source extensions in its default set. A guard in `clew/treescan.py` (`roots_matching_no_file_pattern`) refuses an `--extra-input` root whose files all fail that filter. JS/TS files pass through `claims()` and are parsed by the front end.

**What happens when nothing is declared**

`whole_repo_scope` in `clew/scope.py` takes the whole repository as one root. The excludes come from three sources:

- **Git ignores.** `git ls-files --others --ignored --exclude-standard --directory` runs for the repo, and again for each nested git tree. Git runs through `git_argv` and `git_env`, so a target's `.git/config` cannot execute code.
- **Dot and cache directories.** Any directory whose name starts with `.` (`.git`, `.venv`, and so on) plus `__pycache__` and `node_modules` is pruned. Their paths are passed to doxygen as EXCLUDE entries.
- **Depth limit.** Descent stops at depth 16. Directories past that are recorded and logged rather than walked.

Nested git trees (submodules, vendored clones) are included, not excluded (gh#333). `external.py` tags their rows after the build so answers can tell the codebases apart. Their own top-level dot directories are still pruned.

If git is missing or the directory isn't a repository, nothing is excluded by git, the scope is wider than intended, and the log says so. The repo's Doxyfile no longer sets the INPUT; it supplies only aliases and predefined macros.

**Caveats**

- I did not check how the prose ingestion path picks non-source files such as `.md`. Doxygen's pattern filter does not decide those.
- The tagging in `external.py` and the operator-exclude replay were read, not traced.