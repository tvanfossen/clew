Now I have the full mechanism. This is straightforward, no organizational-principle concerns here (no PII, no IP misuse, purely a code-behavior question), so I'll answer directly.

## What counts as an edge

An edge exists from file A to file B only when **all** of these hold:

1. **A's raw import list contains a string that reduces to B's file stem.** The reduction (`resolve_candidate`) strips, in order: a path prefix (up to the last `/` or `\`), a known source-file extension (drawn from the substrate's registered languages, not hardcoded), then a namespace separator (`::` for Rust-style, or `.` for dotted paths). What survives is compared against every corpus file's `Path::file_stem()`.
2. **The resulting candidate key is unique in the corpus** (`key_counts.get(&candidate) == 1`). If two or more files share that stem — e.g. two different packages each with a `mod.rs`, or `utils.py` next to `utils.js` — the import resolves to **no edge at all**, for *every* file with that ambiguous stem, rather than guessing. The comment/design rationale is explicit: "a wrong edge is worse than a missing one."
3. **The target isn't the importing file itself** — self-imports are dropped (`if target != path`).

Each resolved edge is deduplicated per file pair: `edges` is a `HashMap<String, HashSet<String>>`, so importing the same target twice contributes one edge, and `Ce`/`Ca` count **distinct files**, not raw import statement counts.

## What deliberately does not count

- **Anything outside the corpus** — third-party libraries, stdlib imports, or any import string that doesn't resolve to a file actually being analyzed (e.g. `numpy` in a Python file with no `numpy.py` in the corpus). This is deliberate scope-matching to Robert Martin's classic Ce/Ca/Instability, which is defined *within* a package/corpus boundary — counting externals would push instability toward 1.0 for nearly every file and erase the signal.
- **Ambiguous stem matches**, as above — resolved to zero edges rather than an arbitrary pick.
- **Self-references** — a file "importing itself" (e.g. via a relative path that resolves back to its own stem).
- **Unresolvable dynamic requires** (e.g. `require(someVariable)`) — nothing to match a stem against, so no edge.

## Downstream consequence

The resulting per-file `Ce` is folded back into each function's AIRD score via `apply_aird_ce_multiplier` — so this heuristic resolution isn't just a report field, it directly perturbs a complexity metric. If the resolution under-counts (ambiguous stems, unrecognized import syntax for a language), AIRD for functions in that file is correspondingly under-inflated relative to true coupling.

One thing worth flagging as a limitation rather than a bug: this is **stem-matching, not real module resolution** — it doesn't do actual path resolution (relative `../../` traversal, package.json/Cargo workspace-aware resolution, etc.), so a false negative (missed edge) is more likely than a false positive, by design.
