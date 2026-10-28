Clew has four ways to say what a repository should index, plus a fifth source of facts it reads without being told. When they disagree, the stated ones win, and the rule is a tier ordering rather than "last one wins."

**The ways to say so**

| Tier | Source | What it does |
|---|---|---|
| 1 (explicit) | CLI flags, or the `options` argument for an embedding caller | Replaces the stated layer for that option. Not recorded for replay unless it is a tier-1 statement. |
| 2 (declared) | `.clew.yaml` in the repo root | Replaces the stated layer. Each section mirrors the standalone manifest format for that option. |
| 3 (target-fact) | Facts the repo already wrote, such as a Doxyfile's `ALIASES`/`PREDEFINED`, a generator manifest, or a language entry point | Accumulates. |
| 4 (ecosystem) | Known-ecosystem signatures | Accumulates. |
| 5 (heuristic) | Name-pattern guesses, the built-in floor | Replaced by any stated tier. |

- **Scope** (what gets indexed) has only two tiers: a declared `index_scope:` in `.clew.yaml`, or the whole repository minus what git ignores. The Doxyfile is no longer a scope tier (gh#333). Its `INPUT`, `EXCLUDE*` and `FILE_PATTERNS` are replaced, but it is still read for `ALIASES` and `PREDEFINED`. Only a declaration is a decision about the index.
- **Doxyfile location** can be stated as a `doxyfile:` section, because a repo's documentation target sits outside the `Doxyfile`-in-root/`docs/`/`doc/` convention. The path must exist when stated, or the build would silently fall through to whole-repo synthesis.
- **Build mechanics** (`--scope`, `--index-cache`, `--rebuild`) are per-run facts. They are not declarations.

**When two disagree**

- **Flag vs. declaration:** the flag wins. The file is the standing statement and the flag is a deliberate one-off override.
- **Declaration vs. heuristic:** the declaration wins and the guesses are discarded.
- **Facts (tiers 3–4) are never displaced.** A stated tier only replaces the guesses underneath. So `main` survives even when someone passes `--entry-patterns`, which previously dropped it silently. Tiers 3 and 4 combine identically; the label is cosmetic.
- **Empty means withdrawn, not stated.** `[]` or `{}` falls through to the next tier rather than overriding it. This lets an operator undo a recorded flag without deleting the database.
- **Malformed input:** an unknown top-level section is refused with an error that names the allowed set. A malformed declaration that is otherwise readable degrades to defaults.

The winning tier is recorded in `build_meta`, so the result can be read back, and only tier-1 statements are replayed on later builds.

Caveat: the index flagged the tier resolver and the document resolver as built from an older revision of `clew/tiers.py`, so their line numbers may be slightly off. The behaviour described above comes from their docstrings and tests, which the index does hold.