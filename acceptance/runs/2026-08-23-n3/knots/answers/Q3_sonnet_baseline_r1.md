I have what I need — this is fully self-contained in `src/coupling.rs`.

## What counts as an edge

An edge `A → B` is drawn only when file `A`'s raw import string, after reduction, resolves **unambiguously to exactly one other file in the analyzed corpus**. The resolution pipeline is:

1. **Extraction** — raw import strings per file come from the tree-sitter substrate's `import_sources` (language-agnostic; already strips quotes/angle-brackets, etc.).
2. **Candidate reduction** (`resolve_candidate`) — each import string is whittled down to a single trailing identifier: strip any path prefix (up to the last `/` or `\`), strip a trailing extension *if it matches a known source extension* (`.py`, `.js`, `.h`, etc.), then strip a namespace separator (`::` for Rust, `.` for dotted-package styles like Java).
3. **Match against corpus file stems** (`module_key` = `Path::file_stem`) — every file in the corpus is indexed by its stem, along with how many files share that stem.
4. **Edge fires only if the stem match is unique** (`key_counts == 1`) and the target isn't the file itself (no self-edges).

So a valid edge requires: import → reduces to a stem → exactly one corpus file has that stem → that file isn't the importer.

## What deliberately does *not* count as an edge

- **Anything outside the corpus** — third-party libraries, stdlib, unresolvable dynamic `require`s. The module comment is explicit: Ce/Ca measure coupling *within the analyzed corpus only*, matching the classic Martin Ce/Ca/Instability definition; counting externals would inflate Ce for nearly every file and drown the signal (there's a dedicated test, `external_imports_do_not_create_edges`, e.g. `numpy` in a `.py` file).
- **Ambiguous stem matches** — if two or more corpus files share the same file stem (e.g. `mod.rs` in two different packages, or `utils.py` vs `utils.js`), the import resolves to *no edge at all*, rather than picking arbitrarily. The design rationale stated in the doc comment: "a wrong edge is worse than a missing one." (`ambiguous_stem_resolves_to_no_edge` test.)
- **Self-imports** — `resolve_targets` explicitly skips `target == path`.
- **Duplicate imports of the same target** — the edge set is a `HashSet<String>`, so Ce counts *distinct* files imported, not raw import statement count (importing the same module twice doesn't double Ce).

This makes the whole thing a deliberately conservative, best-effort heuristic rather than real module resolution — no build-system knowledge, no resolution of relative-path semantics beyond a bare stem match, and no partial credit for near-misses.
