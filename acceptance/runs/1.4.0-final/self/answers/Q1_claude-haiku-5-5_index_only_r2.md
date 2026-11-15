The index scope is decided by a declaration if one exists, and otherwise by the whole repository minus what git ignores. The Doxyfile and the doxygen-guard gate no longer decide anything. I answered from the index only; the source bodies were read through the index, not the files.

**How the decision is made**

`derive_scope` in `clew/scope.py` is the single entry point. It resolves to one of two tiers:

```
derive_scope(repo_root)
 ├─ _declared_index_scope(root)      tier 1: .clew.yaml  index_scope:
 │    usable roots → SOURCE_DECLARED
 │    unusable    → _Rejected (warning logged) → whole-repo tier, reason names the rejection
 │    absent/empty → None
 └─ whole_repo_scope(root)           tier 2: SOURCE_WHOLE_REPO
```

- **Tier 1, a declaration.** The repo's `.clew.yaml` can carry `index_scope:` with `roots:` and `excludes:`. The roots are repo-relative. A declared root is taken at its word and never walked. A root that does not exist on disk is dropped with a warning. `roots` is required: `excludes` alone does nothing. A misspelled key inside the block (for example `exclude:` for `excludes:`) refuses the whole declaration by name rather than being silently ignored. A `sub_index` block can further trim a named sub-index. This is the only tier that is a decision about the index.
- **Tier 2, the whole repository.** Its single root is the repo root. Excludes come from `git ls-files --others --ignored --exclude-standard --directory`, run through `git_argv`/`git_env` so a cloned repo's own config cannot execute code. The nested git trees found by the walk are included, and their own `.gitignore` files are honoured too. Dot and cache directories are pruned as well.

**What is deliberately not an input**

- **The Doxyfile `INPUT`** is not used for scope since gh#333. The rationale is that it is a documentation target, not a reasoning boundary. A repo that ships a Doxyfile still has its `ALIASES` and `PREDEFINED` read, but its `INPUT` is replaced. The docstring cites Mbed-TLS, whose Doxyfile indexes 1,571 header declarations and none of the 108 `library/*.c` implementations.
- **The doxygen-guard `files:` pattern** is the gate's boundary: it says what must be documented. A test (`test_a_gate_pattern_alone_derives_no_index_scope`) asserts that it supplies no roots.
- **Nested git trees** are not excluded. They are indexed, and `external.py` tags their rows so that two codebases in one index can be told apart in an answer.

**When nothing is declared**

Nothing is declared means the whole-repo tier applies, and the reason string records it. The `_declaration_note` text says why nothing was found. A test (`test_empty_or_absent_index_scope_falls_back_to_the_whole_repo`) confirms that `index_scope: {roots: []}` falls through to the whole repo rather than producing an empty index. Those are the zero-config defaults, and they make a repo with no config fully indexable.

**What the index reports about what it left out**

`_not_indexed_scope` in `clew/cli.py` counts scanned files whose type the build holds no rows for, stamps them as `not_indexed` and `not_indexed_count`, and names the top extensions. This distinguishes "the symbol does not exist" from "this file type is not indexed" from "this path is outside the declared scope." An index with nothing missed, or one built without walking the tree, gets no such stamp.

**What I could not confirm**

- `propose_declaration` was denied permission in this session, so I could not see its proposed defaults.
- The source of the file-extension filter (the `scope.extensions` the docstring refers to) is not in the indexed symbols I read. I do not know how it chooses extensions.
- `_SKIP_DIR_NAMES` is the list of directory names pruned in the whole-repo tier, but I did not read its contents.