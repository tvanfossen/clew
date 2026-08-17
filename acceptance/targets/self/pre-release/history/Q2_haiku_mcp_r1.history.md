# Q2 — mcp — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll search the index for how this codebase handles nested repositories.

### 1. `mcp__doxyguard-db__search`
- **asked:** target, text
### 2. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":2,"results":[{"name":"tests/test_git_env_isolation.py","kind":"file","file":"tests/test_git_env_isolation.py","brief":"The suite must not inherit the repository it is being committed to…

- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"gitdir external_root","note":"No matching symbols for 'gitdir external_root'. This is NOT an error and NOT a malformed call, and it is NOT a definitive negativ…

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":9,"results":[{"name":"external_root","kind":"variable","file":"doxyguard_db/shared_key_edges.py"},{"name":"_external_roots","kind":"function","file":"doxyguard_db/query/graph.py","brief…

### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"prose matches","count":18,"results":[{"file_path":"tests/test_git_env_isolation.py","heading":"tests/test_git_env_isolation.py — file-level documentation","snippet":"…them a >>nested<<-git-tree test, because the…

### 5. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"external_roots","subject_kind":"function","name":"external_roots","rowid":1947,"signature":" list[str] doxyguard_db.external.external_roots(Path repo_root)","file":"doxyguard_db/external.py","line_start":147,…

### 6. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"_owning_root","subject_kind":"function","name":"_owning_root","rowid":1948,"signature":" str doxyguard_db.external._owning_root(str name, list[str] roots)","file":"doxyguard_db/external.py","line_start":179,"…

### 7. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
### 8. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"dependency_roots","subject_kind":"function","name":"dependency_roots","rowid":2875,"signature":" list[Path] doxyguard_db.scope.dependency_roots(Path repo_root)","file":"doxyguard_db/scope.py","line_start":277…

- **got:** {"subject":"nested_repo_roots","subject_kind":"function","name":"nested_repo_roots","rowid":2874,"signature":" list[Path] doxyguard_db.scope.nested_repo_roots(Path repo_root)","file":"doxyguard_db/scope.py","line_start":…

### 9. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
### 10. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"_nested_repos_under","subject_kind":"function","name":"_nested_repos_under","rowid":2867,"signature":" list[Path] doxyguard_db.scope._nested_repos_under(Path input_root)","file":"doxyguard_db/scope.py","line_…

- **got:** {"subject":"_is_dependency_of_parent","subject_kind":"function","name":"_is_dependency_of_parent","rowid":2876,"signature":" bool doxyguard_db.scope._is_dependency_of_parent(Path directory)","file":"doxyguard_db/scope.py…

### 11. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"_holds_git_tree","subject_kind":"function","name":"_holds_git_tree","rowid":2879,"signature":" bool doxyguard_db.scope._holds_git_tree(Path directory)","file":"doxyguard_db/scope.py","line_start":529,"line_en…

### 12. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"whole_repo_scope","subject_kind":"function","name":"whole_repo_scope","rowid":2871,"signature":" DerivedScope doxyguard_db.scope.whole_repo_scope(Path repo_root, Path|str|None guard_config=None)","file":"doxy…

### 13. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"subject":"stamp_external_provenance","subject_kind":"function","name":"stamp_external_provenance","rowid":1945,"signature":" tuple[int, list[str]] doxyguard_db.external.stamp_external_provenance(Path db_path, Path repo…

### 14. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/scope.py
- **got:** 529	def _holds_git_tree(directory: Path) -> bool: 530	    """A SUBMODULE'S `.git` IS A FILE, NOT A DIRECTORY, and missing that made the 531	    whole nested-tree feature blind to the case it was built for. A `git submodu…

### 15. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_external_provenance.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Per-file EXTERNAL provenance (gh#335) — the tag, and what must NOT move because of it. 3	 4	gh#333 admits nested git trees into the index. That trade is only honest if two 5	things h…

### 16. `Bash`
- **asked:** command=cd ~/ddb-targets/self && grep -n "def test_" tests/test_external_provenance.py | head -20
- **got:** 139:def test_only_a_directory_with_its_own_git_tree_is_external(tmp_path: Path) -> None: 170:def test_a_stray_developer_clone_the_parent_tracks_is_first_party(tmp_path: Path) -> None: 218:def test_admitting_a_submodule_l…

### 17. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_external_provenance.py
- **got:** 139	def test_only_a_directory_with_its_own_git_tree_is_external(tmp_path: Path) -> None: 140	    """THE RULE, stated as a discrimination rather than as a match. Both directories 141	    below are named `vendor/...`; only…

### 18. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_external_provenance.py
- **got:** 170	def test_a_stray_developer_clone_the_parent_tracks_is_first_party(tmp_path: Path) -> None: 171	    """THE NEGATIVE HALF OF gh#352, and the case that forced the predicate split. Both 172	    directories here hold a re…

### 19. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_external_provenance.py
- **got:** 401	def test_a_submodule_whose_git_is_a_file_is_detected(tmp_path: Path) -> None: 402	    """THE CASE THE WHOLE FEATURE WAS BUILT FOR, and the one every other fixture in 403	    this file gets wrong. A `git submodule` ch…

### 20. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/external.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Per-file EXTERNAL provenance — which indexed files belong to someone else's repo. 3	 4	gh#333 stopped cutting nested git trees out of the index, because a `chain_trace` 5	that stops …

### 21. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/external.py
- **got:** 200	## @req REQ-DDB-INDEX-005 201	def stamp_external_provenance(db_path: Path, repo_root: Path) -> tuple[int, list[str]]: 202	    """FAILS SOFT, like every other measurement stamped onto an already-successful 203	    bui…

### 22. `Bash`
- **asked:** command=grep -n "stamp_external_provenance\|external_root_column" doxyguard_db/*.py doxyguard_db/**/*.py 2>/dev/null | head -20
- **got:** doxyguard_db/cli.py:88:from .external import EXTERNAL_ROOTS_META_KEY, stamp_external_provenance doxyguard_db/cli.py:1428:    external_tagged, external = stamp_external_provenance(output, repo_root) doxyguard_db/external.…

### 23. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 1420	    ## only do that once `supplementary_docs` is populated. Measured on mbedtls: run 1421	    ## before this line, 27 substantive `.md` files read 100% barren and inflate the 1422	    ## headline ratio. `report_inde…

**Reasoning.** Now let me verify the tests to confirm the different real-world cases:

### 24. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_index_scope_inheritance.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Every index scope names its tier, and every index scope is contained. 3	 4	gh#20. The tier a scope came from is the whole answer to "was this boundary 5	chosen": a DECLARED scope is …

**Reasoning.** ## ANSWER

This codebase treats nested repositories as **indexed but distinctly tagged**. Here's the architecture:

### **What It Does**

The codebase includes nested repositories in the full index (since gh#333: `doxyguard_db/scope.py:200-244`), but tags each indexed file to mark which external repository it belongs to. This allows:
- Cross-boundary traversal (chain_trace and call graphs cross submodule boundaries)
- Accurate provenance reporting (each file knows its owner)
- First-party aggregates (coverage/orphan counts exclude external files by default: `doxyguard_db/external.py:34-39`)

#

---

## Final answer as submitted

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
