# Q2 — mcp — haiku — run 1

## ANSWER

This codebase treats nested repositories as **indexed but distinctly tagged**. Here's the architecture:

### **What It Does**

The codebase includes nested repositories in the full index (since gh#333: `doxyguard_db/scope.py:200-244`), but tags each indexed file to mark which external repository it belongs to. This allows:
- Cross-boundary traversal (chain_trace and call graphs cross submodule boundaries)
- Accurate provenance reporting (each file knows its owner)
- First-party aggregates (coverage/orphan counts exclude external files by default: `doxyguard_db/external.py:34-39`)

### **How It Decides**

Two predicates determine the classification (`doxyguard_db/scope.py:529-619`):

**1. Detection: `_holds_git_tree()` checks for the presence of `.git`**
```
(directory / ".git").exists()  [doxyguard_db/scope.py:557]
```
This returns True for:
- A nested clone (`.git` directory)
- A submodule (`.git` file containing `gitdir:` pointer: `doxyguard_db/scope.py:532`)
- A git worktree (`.git` file: `doxyguard_db/scope.py:543`)

**2. Declaration: `_is_dependency_of_parent()` asks git whether the parent claims ownership**
```
git ls-files -s <directory.name> | grep "160000"  [doxyguard_db/scope.py:605-619]
```
Mode `160000` means gitlink (declared submodule). Mode `100644`/`100755` means the parent TRACKS the files—first party. The **fail-closed rule is inverted here**: when git cannot answer, the answer is "first party" (`doxyguard_db/scope.py:574-576`), because tagging the repo's own code as external would make it vanish from first-party counts and depend on the developer's working copy.

### **Where It's Applied**

**Scope phase** (`doxyguard_db/scope.py`):
- `nested_repo_roots(repo_root)` finds all directories with `.git`, bounds the search to avoid descending into git object stores (`doxyguard_db/scope.py:489-523`)
- `dependency_roots(repo_root)` filters those to only gitlinks (`doxyguard_db/scope.py:277-294`)
- `whole_repo_scope()` includes nested trees in the index by default and respects each tree's `.gitignore` (`doxyguard_db/scope.py:221-228`)

**Tagging phase** (after the index is built):
- `stamp_external_provenance(db_path, repo_root)` runs during the build pipeline (`doxyguard_db/cli.py:1428`)
- For each indexed file, it determines the owning external root via path-prefix matching with `/` separator boundary (`doxyguard_db/external.py:244`)
- Updates the `external_root` column in the `path` table (`doxyguard_db/external.py:246`)
- Also marks unresolved `#include` targets that refer to no disk file (`doxyguard_db/external.py:247-248`)

### **How Real-World Nested Repositories Appear**

The tests (`tests/test_external_provenance.py`) validate these cases:

**1. Standard submodule with `.git` file** (`test_a_submodule_whose_git_is_a_file_is_detected:401-427`)
- A `git submodule` checkout writes a 44-byte pointer file: `gitdir: ../../.git/modules/<name>`
- Detected as `.git` file (not directory)
- Tagged external if declared in `.gitmodules`
- **Important historical note**: Earlier versions tested only `".git" in dirnames` and missed ALL submodules, while reporting 28 nested clones when measuring entropic (which had only 1 submodule) because of unreadable directories in git object stores (`doxyguard_db/scope.py:537-541`)

**2. Developer's stray clone** (`test_a_stray_developer_clone_the_parent_tracks_is_first_party:170-213`)
- A developer runs `git clone` inside a directory whose files the parent repository tracks
- Has a real `.git` directory but is NOT a gitlink (mode 100644/100755, not 160000)
- Stays first party, because tagging it would make the same commit index differently depending on who built it (`doxyguard_db/scope.py:580-583`)
- Real example: entropic had three directories with `.git` but only one declared as a gitlink (`doxyguard_db/scope.py:585-589`)

**3. Vendored code without `.git`** (`test_only_a_directory_with_its_own_git_tree_is_external:139-166`)
- A copied-in third-party file like `vendor/copied/header_only.h` with no git tree
- Stays first party, because the repo committed it and owns it
- No name-based detection (no `vendor/` or `third_party/` heuristic): `doxyguard_db/external.py:17-21`

**4. Path-prefix collisions** (`test_a_shared_path_prefix_does_not_misattribute_a_sibling_tree:431-450`)
- `vendor/lib` and `vendor/lib-utils` are separate external roots
- Attribution uses path-separator-aware matching: `name.startswith(f"{root}/")`, not bare `startswith` (`doxyguard_db/external.py:179-194`)

**5. External tree with no indexed files** (`test_a_nested_tree_with_no_indexed_file_is_not_reported:368-385`)
- Detected but not reported in `external_roots` metadata because it owns no row
- Prevents publishing directory names of excluded subtrees (`doxyguard_db/external.py:256-265`)

## Gaps

None identified. The index answers fully on the detection mechanism, decision criteria, application points, and real-world cases.
