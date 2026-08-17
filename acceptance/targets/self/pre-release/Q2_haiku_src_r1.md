# Q2 — src — haiku — run 1

## ANSWER

This codebase indexes nested repositories but **tags them as external** rather than excluding them. The decision is made in two independent checks, and the application occurs during the build pipeline.

### WHAT THE CODEBASE DOES

**Index nested trees, tag files by ownership.** `external.py:13-21` states the rule:

> A directory with its own git tree (a `.gitmodules` entry, or a directory containing `.git`) → EXTERNAL. Anything else this repo tracks → FIRST PARTY. NO NAME MATCHING.

Nested trees are indexed because `external.py:4-9` explains that excluding them loses information: a `chain_trace` that stops at a submodule boundary answers "this call leaves the repo" when it could answer what the call actually does. Instead, files are tagged with `dg_external_root` on the `path` table and files themselves remain queryable.

### HOW IT DECIDES

**Two independent predicates, both required.**

**Step 1 — Filesystem detection:** `scope.py:557` — `(directory / ".git").exists()`. This covers:
- Clone directories with `.git/` as a directory
- Submodules with `.git` as a 44-byte pointer file (the gitdir reference)
- Git worktrees with `.git` as a file

**Step 2 — Ownership check:** `scope.py:619` — `git ls-files -s <path>` on the parent directory. Only if the parent records the child at mode `160000` (a gitlink) is it tagged external. This is critical: `scope.py:578-583` explains why:

> A `.git` in a directory says somebody has a repository THERE; it does not say the parent treats that directory as somebody else's code. The two diverge in a case that is common: a developer clone left inside a directory whose files the parent TRACKS.

Real measurement on entropic: three nested trees detected, but `.gitmodules` declared only one. `git ls-files -s examples/explorer` returned mode 100644 (ordinary files), not 160000, so those two are entropic's own committed code.

### WHERE THE DECISION IS APPLIED

The decision is applied in `cli.py:1428`: `external_tagged, external = stamp_external_provenance(output, repo_root)`, which runs **after** the index is built but **before** coverage is reported (`cli.py:1430`).

`external.py:201-246` walks every indexed file, checks whether it falls inside an `external_root`, and stamps the `dg_external_root` column. Coverage aggregates then default to FIRST PARTY by filtering this column, while traversal queries (`chain_trace`, `callers`, `callees`) cross the boundary freely.

### VALIDATION AGAINST REAL NESTED REPOSITORY FORMS

| Form | Detection | Tagging | Verified By |
|------|-----------|---------|------------|
| Submodule (`.git` is 44-byte file) | ✓ exists() covers files (`scope.py:543`) | ✓ `git ls-files -s` returns 160000 | `test_external_provenance.py:399-426` |
| Clone (`.git` is directory) | ✓ exists() covers directories | ✓ if parent declared as gitlink | `test_external_provenance.py:139-165` |
| Stray developer clone (has `.git`, parent tracks files) | ✓ detected by `_holds_git_tree` | ✗ gitlink check fails (`git ls-files` returns 100644) | `test_external_provenance.py:168-213` (measured on entropic) |
| Copied-in code with no `.git` | ✗ no `.git` to detect | N/A | `test_external_provenance.py:139-165` asserts "vendor/copied/header_only.h stays first party" |
| Git worktree (`.git` is file) | ✓ exists() covers worktrees (`scope.py:543`) | ✓ if parent declared as gitlink | Noted but not explicitly tested |
| Unresolvable `#include` (bare filename, no file on disk) | ✗ not resolved | ✗ matched separately via `dg_unresolved` column | `test_external_provenance.py:326-359` |

**The critical fix:** Prior to gh#352, the detector only checked `".git" in dirnames` (looking for directories). On entropic, which wraps llama.cpp as an actual submodule, this reported **28 nested trees** while missing `extern/llama.cpp` — the submodule it was built to detect (`scope.py:531-541`). Every test fixture used `.git` directories, so nothing in the suite could catch the defect.

## Gaps

None. The source code is complete and the decision logic is well-documented with extensive integration tests covering all major cases where nested repositories appear on disk.
