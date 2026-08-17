# Q2 — mcp — sonnet — run 1

## What the codebase does

**Rule (doxyguard_db/external.py:11-15):** a directory holding its own git tree is `EXTERNAL`; everything else the repo tracks is `FIRST PARTY`. Explicitly **no name matching** — `vendor/`/`third_party/` conventions are rejected as a detector because a copied-in third-party file with no git tree of its own is still first party (`external.py:17-21`).

But there's a second, narrower question layered on top: not just "is there a separate git tree here" but "did *this* repo declare it as a dependency" (a submodule gitlink) vs. "someone left a stray clone inside a directory this repo already tracks."

## How it decides — two predicates, deliberately kept separate

1. **`_holds_git_tree`** (`doxyguard_db/scope.py:529-557`) — "is there a separate git tree here at all?" Test: `(directory / ".git").exists()`. Uses `exists()`, not `is_dir()`, specifically because a submodule's `.git` is a **file** (a `gitdir: ../../.git/modules/<name>` pointer), not a directory — the docstring records that the old `".git" in dirnames` form was blind to every submodule while still reporting 28 "hits" on nested clones, which made it look correct (`scope.py:530-541`). This walk (`_nested_repos_under`, `scope.py:489-521`) is bounded — stops descending at any nested tree it finds, and at `_MAX_DEPTH = 16` (`scope.py:61`) — and treats an unreadable directory as a **warned gap**, not a clean negative (`_warn_unwalkable`, `scope.py:626-632`).

2. **`_is_dependency_of_parent`** (`scope.py:565-619`) — "does the *parent* repo record this directory as a gitlink?" Runs `git ls-files -s -- <dir>` from the parent's cwd and checks for mode `160000` (the gitlink mode). This is the ownership filter layered on top of the tree-detection walk.

These compose into two different lists (`scope.py:250-292`):
- `nested_repo_roots` = every directory with its own `.git` (clones, submodules, worktrees) — used for **descent**, e.g. respecting each nested tree's own `.gitignore`, since `git ls-files` stops at any tree boundary.
- `dependency_roots` = the subset of those that are gitlinks — used for **ownership/tagging**.

## Where the decision is applied

`external.py:external_roots` (`external.py:147-170`) wraps `dependency_roots` (not the wider `nested_repo_roots`) specifically so that "declared as somebody else's code" and "happens to be a separate git tree" don't get conflated — the docstring cites a measured 3-vs-1 discrepancy on a real repo where two tracked example directories had their own `.git` but were not submodules (`scope.py:585-589`).

`stamp_external_provenance` (`external.py:201-280`) then tags every indexed file row: `path.dg_external_root` gets the owning root's repo-relative path (never absolute — `_relative_root`, `external.py:121-139`, explicitly to avoid the machine-layout leak that forced an earlier build-version bump). Matching is prefix-on-separator (`_owning_root`, `external.py:179-192`) to avoid `vendor/llama` false-matching `vendor/llama-utils`. Queries (`chain_trace`, `callers`, `callees`, `dossier`) cross the boundary freely; only aggregates (coverage, orphan counts, file counts) filter to first-party by default (`external.py:34-39`).

## Checking the decision against how nested repos actually appear on disk

Ways a nested repository can appear, and whether `_holds_git_tree`'s `(directory / ".git").exists()` catches each:

| Form | `.git` shape | Caught? |
|---|---|---|
| Standalone clone | directory | Yes |
| Submodule checkout | file (`gitdir:` pointer) | Yes — this is the case the fix in `scope.py:529-557` targeted |
| Linked worktree | file (`gitdir:` pointer) | Yes, per the docstring's own claim (`scope.py:543`) |
| Symlinked `.git` | symlink to dir/file | Yes — `Path.exists()` follows symlinks |
| **Bare repository** (no working tree; `HEAD`/`refs`/`objects` sit directly in the directory, no `.git` entry at all) | none | **No** — `_holds_git_tree` only ever checks for a `.git` entry; a bare repo has none, so a bare nested repo would silently read as first party |
| **Broken/dangling symlinked `.git`** | symlink to a missing target | **No** — `Path.exists()` returns `False` for a broken symlink, so this would also read as first party |
| Gitlink recorded but working directory not checked out (submodule declared, never initialized) | no `.git` at all in that path | **No**, but this is arguably correct — there's no tree there to misattribute either way |

The two gaps that are real detector blind spots — bare repositories and broken/dangling `.git` symlinks — are not mentioned anywhere in `scope.py` or `external.py`'s extensive commentary, which otherwise documents every other edge case it hit (submodule pointer files, stray clones inside tracked directories, unresolved `#include` rows) in detail. Nothing in the code or comments suggests these were considered.

## Gaps

- I did not find any test file specifically exercising a bare-repository or broken-symlink case (only `tests/test_git_env_isolation.py` came up in search, which covers `GIT_DIR` environment isolation, not the `.git`-shape detection itself). I did not exhaustively grep the test suite for `_holds_git_tree`/`_nested_repos_under` coverage beyond what search surfaced — a full test-file read would be needed to confirm whether bare repos are tested and intentionally out of scope, or simply unconsidered.
- The MCP index's symbol search (`search`) could not resolve `_holds_git_tree`/`_nested_repos_under`/`dependency_roots` by name (empty results), so this answer was built by falling back to direct source reading via `Grep`/`Read` after the index pointed me at the two relevant files (`external.py`, `scope.py`) through file-level doc search. That fallback is itself a result: the index's file-doc search located the right files quickly, but function-level lookup by these specific names did not resolve.
