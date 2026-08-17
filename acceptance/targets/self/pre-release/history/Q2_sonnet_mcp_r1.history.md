# Q2 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"doxyguard_db/scope.py","kind":"file","file":"doxyguard_db/scope.py","brief":"Resolve the index scope: a declaration, else the whole repository. TWO tiers, and the …

### 2. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"dg_external_root","note":"No matching symbols for 'dg_external_root'. This IS a definitive empty result from the database, NOT an error and NOT a malformed cal…

### 3. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"doxyguard_db/external.py","kind":"file","file":"doxyguard_db/external.py","brief":"Per-file EXTERNAL provenance — which indexed files belong to someone else's repo…

### 4. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"gitdir pointer file","note":"No matching symbols for 'gitdir pointer file'. This is NOT an error and NOT a malformed call, and it is NOT a definitive negative …

### 5. `mcp__doxyguard-db__dossier`
- **asked:** kind=file
- **got ⚠ error:** Error executing tool dossier: Subject kind 'file' names no dossier subject: a file has no dossier — its documentation is `search(corpus='prose')`.

### 6. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"doxyguard_db/external.py","kind":"file","file":"doxyguard_db/external.py","brief":"Per-file EXTERNAL provenance — which indexed files belong to someone else's repo…

### 7. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"is_nested_git_tree","note":"No matching symbols for 'is_nested_git_tree'. This IS a definitive empty result from the database, NOT an error and NOT a malformed…

### 8. `Grep`
- **asked:** pattern=def.*nested|def.*external_root|dirnames|\.git, path=~/ddb-targets/self/doxyguard_db/external.py
- **got:** 13:    a directory with its own git tree (a `.gitmodules` entry, or a directory 14:    containing `.git`)  ->  EXTERNAL 121:def _relative_root(root: Path, nested: Path) -> str: 147:def external_roots(repo_root: Path) -> …

### 9. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/external.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Per-file EXTERNAL provenance — which indexed files belong to someone else's repo. 3	 4	gh#333 stopped cutting nested git trees out of the index, because a `chain_trace` 5	that stops …

### 10. `Grep`
- **asked:** pattern=def dependency_roots|def nested_repo_roots|\.gitmodules|is_dir\(\)|is_file\(\), path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 250:def nested_repo_roots(repo_root: Path) -> list[Path]: 277:def dependency_roots(repo_root: Path) -> list[Path]: 586:    external while `.gitmodules` declares ONE. `git ls-files -s examples/explorer

### 11. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 230	    return DerivedScope( 231	        source=SOURCE_WHOLE_REPO, 232	        reason=( 233	            f"no {INDEX_SCOPE_SECTION} is declared for this repo — " 234	            f"{_guard_config_note(root, guard_config)} …

### 12. `Grep`
- **asked:** pattern=def _nested_repos_under|def _is_dependency_of_parent|def _skip_dir|\.gitmodules|\.git\b, path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 124:def _skip_dir(name: str) -> bool: 256:    A directory holding `.git` is a DIFFERENT repository. That is the ONLY test, and 388:    and tagged, skipping it would leave its `.git` object store and its caches as the 389…

### 13. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 480	        excludes=tuple(excludes), 481	    ) 482	 483	 484	## @brief Directories holding a `.git` strictly beneath one declared root. 485	## @param input_root Declared INPUT root to search under. 486	## @return Absolu…

### 14. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 608	            capture_output=True, 609	            text=True, 610	            check=False, 611	            env=git_env(), 612	        ) 613	    except OSError: 614	        return False 615	    if proc.returncode != 0 o…

### 15. `Grep`
- **asked:** pattern=_MAX_DEPTH =, path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 61:_MAX_DEPTH = 16

**Reasoning.** ## What the codebase does

**Rule (doxyguard_db/external.py:11-15):** a directory holding its own git tree is `EXTERNAL`; everything else the repo tracks is `FIRST PARTY`. Explicitly **no name matching** — `vendor/`/`third_party/` conventions are rejected as a detector because a copied-in third-party file with no git tree of its own is still first party (`external.py:17-21`).

But there's a second, narrower question layered on top: not just "is there a separate git tree here" but "did *this* repo declare it as a dependency" (a submodule gitlink) vs. "someone left a stray clone inside a directo

---

## Final answer as submitted

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
