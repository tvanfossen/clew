There are four ways to tell clew how to index a repository, and when two of them disagree the higher tier wins, with the rule depending on the option.

**The ways to say so**

| Tier | Source | Notes |
|---|---|---|
| 1 (explicit) | CLI flags such as `--declare FILE`, `--exclude PATH`, `--shared-key-patterns`, or the structured `options` argument for embedding callers | Applies to one build. Recorded, and replayed on later rebuilds. |
| 2 (declared) | The repo's own `.clew.yaml`, with sections like `index_scope`, `preprocessor`, `requirements`, `guard` | The standing declaration, discovered from `--repo-root`. |
| 3 (target-fact) | Facts someone already wrote down: language, platform, the target's own manifests | Accumulates. No stated tier can remove it. |
| 4 (ecosystem) | Known-ecosystem signatures, such as default key-alias prefixes | Accumulates. A declaration can add to it but not remove it. |
| 5 (heuristic) | Name-pattern guesses | The layer a stated tier displaces. |

A `--declare` document uses the same schema as `.clew.yaml`. `export` writes the stated options back out as a declaration, and `propose_declaration` drafts a `.clew.yaml` entirely as comments, so nothing changes until someone uncomments it. I did not run that proposal: the tool call was denied permission, so I have not seen what it would draft for this repo.

**When two disagree**

- For a layered option, the combination rule is `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. A stated value from tier 1 or tier 2 replaces the guesses but never the facts or ecosystem defaults.
- If a CLI flag and the `.clew.yaml` both state the same option, the flag wins and the declaration is ignored for that build. The index records which tier won.
- An empty explicit value is a withdrawal, not a statement. `[]` falls through to the declaration and then to the guesses, which lets an operator undo a recorded flag without deleting the database.
- Some options are deliberately not competing. For shared-key alias prefixes, a manifest passed by flag and the declared dispatch section are unioned, so passing `--shared-key-patterns` does not silently drop the repo's declared wrapper prefixes. The flag only changes the label recorded for the winning tier.
- `--scope` is no longer a flag. Scope is set through the declared `index_scope` section or the typed build surface.

**Limits of this answer**

I could not read the full `tiers.py` file doc or `buildoptions.py` verbatim. The index does not hold them as named symbols, so the table above is assembled from search snippets and the `resolve_layered` docstring. The tier-1 and tier-2 rows and the tier-5 displacement are confirmed; the exact wording of the other rows is not.