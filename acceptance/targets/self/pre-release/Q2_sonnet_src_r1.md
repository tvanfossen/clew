# Q2 — src — sonnet — run 1

## Summary

The pipeline treats a nested repository as a first-class case rather than something to strip out. It **admits and indexes** nested trees, but tags every file that belongs to one so that aggregate metrics (coverage, orphan/file counts) can still separate the two codebases, while traversal queries (`callers`/`callees`/`chain_trace`) freely cross the boundary (`doxyguard_db/external.py:1-43`).

## What decides "is this a nested repository"

The test is purely structural, never name-based: **a directory holding its own `.git` entry is a different repository** (`doxyguard_db/scope.py:256-260`). `vendor/`/`third_party/` naming is explicitly rejected as a signal (`doxyguard_db/external.py:17-21`).

The check itself, `_holds_git_tree`, is `(directory / ".git").exists()` (`doxyguard_db/scope.py:529-557`) — `exists()` rather than `is_dir()`, because it must cover:
- a standalone clone (`.git` directory),
- a `git submodule` checkout, whose `.git` is a **44-byte pointer file** (`gitdir: ../../.git/modules/<name>`), and
- a git worktree's `.git` file (`doxyguard_db/scope.py:543`).

The walk that applies this test, `_nested_repos_under` (`doxyguard_db/scope.py:489-521`), is a **bounded `os.walk`**, not `rglob`: it stops descending the moment it finds a `.git`, stops at a depth limit, and treats any unreadable directory as a *warned gap*, never a silent "no nested repo found" (`doxyguard_db/scope.py:490-494`, `622-632`).

That raw set — `nested_repo_roots` (`doxyguard_db/scope.py:250-269`) — answers only "is there a separate git tree here." A second, narrower function, `dependency_roots` (`doxyguard_db/scope.py:277-292`), filters that set down to trees the **parent repo itself declares** as a dependency, via `_is_dependency_of_parent` (`doxyguard_db/scope.py:565-619`), which runs `git ls-files -s -- <dir>` in the parent and checks for the gitlink mode `160000`. This distinguishes:
- a true submodule (mode `160000` in the parent's index) → external, from
- a stray developer clone sitting inside a directory the parent **tracks as ordinary files** (mode `100644`) → first party, because the parent committed and owns those files regardless of what happens to be checked out there (`doxyguard_db/scope.py:578-593`).

## Where the decision is applied

1. **Descent during whole-repo scoping** (`doxyguard_db/scope.py:383-405`): a nested repo is walked *into* (not skipped) so its own `.git` object store and caches get pruned like any dot-directory, rather than being left unpruned in the index.
2. **Tagging after the build**, `stamp_external_provenance` (`doxyguard_db/external.py:201-280`), called from the CLI pipeline right after AST symbol recovery and before coverage reporting (`doxyguard_db/cli.py:1428`, ordering justified at `cli.py:1424-1427`). It:
   - computes `external_roots()` — a thin wrapper over `dependency_roots` (`doxyguard_db/external.py:147-170`),
   - stamps a `dg_external_root` column on every `path` row whose repo-relative name falls under one of those roots, matched by path-segment prefix, never bare `startswith` (`doxyguard_db/external.py:179-192`),
   - separately stamps `dg_unresolved` on rows that don't correspond to any real file on disk (doxygen's bare-filename `#include` misses), so those don't get miscounted as first-party (`doxyguard_db/external.py:100-104`, `213-221`, `247-248`).
3. **Consumers**: coverage/orphan/file-count aggregates filter to first-party by default; `chain_trace`/`callers`/`callees`/`dossier` do not filter at all (`doxyguard_db/external.py:34-39`).

## Checking the decision against how a nested repo actually appears on disk

I checked the fixtures in `tests/gitfixture.py` and `tests/test_external_provenance.py` against the forms of nested-repo on-disk representation:

| On-disk form | Covered? | Evidence |
|---|---|---|
| Standalone clone (`.git` is a directory) | Yes — but classified first-party unless the parent's index records a gitlink | `tests/test_external_provenance.py:170-201` (`test_a_stray_developer_clone_the_parent_tracks_is_first_party`) |
| `git submodule` checkout (`.git` is a pointer **file**) | Yes, explicitly regression-tested | `tests/test_external_provenance.py:401-425` (`test_a_submodule_whose_git_is_a_file_is_detected`), `doxyguard_db/scope.py:529-541` documents this was previously broken (missed real submodules on entropic, detected 28 false positives instead) |
| Git worktree (`.git` is a file pointing at `.git/worktrees/...`) | Claimed covered by the same `exists()` check (`doxyguard_db/scope.py:543`), but I found **no dedicated test fixture** building an actual `git worktree add` case — only the submodule-pointer-file shape is exercised |
| Uninitialized/gitlink-only submodule (declared in the parent's index at mode `160000` but never `git submodule update`'d, so no `.git` exists on disk at all) | **Not detected as a nested tree** — `_holds_git_tree` requires a `.git` entry to exist; an uninitialized submodule directory is empty on disk, so the walk sees nothing to tag. This is a real edge the code doesn't seem to consider, though it's also low-impact since an uninitialized submodule contributes zero indexed files. |
| Bare repository nested inside (the directory itself contains `HEAD`/`refs`/`objects` directly, with no `.git` subentry — it *is* the git dir) | **Not detected.** `_holds_git_tree` only checks for a `.git` child; a bare repo has no such child, so this walk would not recognize it as a separate tree at all, and its files would be walked and indexed as ordinary first-party content. I found no test or code comment acknowledging this case. |

## Gaps

- I could not find a test exercising an actual `git worktree add`-produced nested tree (only the submodule-style pointer-file `.git` is fixture-tested), so I can't confirm the "covers a worktree's `.git` file too" claim at `doxyguard_db/scope.py:543` beyond the code comment itself.
- I did not find any handling or acknowledgment (code or tests) of a **bare repository** nested on disk, nor of an **uninitialized submodule** (gitlink recorded but not checked out). Both would evade `_holds_git_tree`'s `.git`-entry check. I did not find any open issue/comment discussing these as known limitations, so I can't say whether they're accepted gaps or simply unconsidered.
- I did not trace whether `_nested_repos_under`'s depth limit (`_MAX_DEPTH`, referenced at `doxyguard_db/scope.py:511-519` but its numeric value defined elsewhere) could itself hide a deeply-nested repository; I did not locate and read the constant's definition.
