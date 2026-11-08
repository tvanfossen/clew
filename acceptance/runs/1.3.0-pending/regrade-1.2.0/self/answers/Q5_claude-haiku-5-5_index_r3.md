There are four ways to tell clew how to index a repo, and they stack in tiers. A stated value from a higher tier displaces the lower stated tier, but never the facts or ecosystem layers.

**The ways to say so**

| Route | Tier | Combines by | Notes |
|---|---|---|---|
| CLI flag (`--shared-key-patterns`, `--thread-patterns`, `--entry-patterns`, `--doxyfile`, `--extra-input`, …) | 1, explicit | Replaces the stated layer | Only a tier-1 statement is recorded for replay on later builds. |
| `options` argument for embedding callers (`clew/buildoptions.py`) | 1, explicit | Same as the flag | Lets MCP callers state values. The vocabulary matches `.clew.yaml`. |
| `.clew.yaml` at the repo root | 2, declared | Replaces the stated layer | Read by both the CLI and MCP through `--repo-root`. Sections mirror the standalone manifest formats. |
| Target's own facts: Doxyfile `ALIASES`/`PREDEFINED`/filters, generator manifests, language or platform entry points | 3, target-fact | Accumulates | Never displaced by any stated tier. |
| Known ecosystem signatures (UDM, ingot) | 4, ecosystem | Accumulates | Same combination rule as tier 3. |
| Built-in name-pattern guesses | 5, heuristic | Replaced by any stated tier | The floor. |

The rule is `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. The short version is that you can correct our guesses, but you cannot un-discover a fact.

**What happens when they disagree**

- **Flag vs. declaration:** the flag wins for that option. The `.clew.yaml` value is not deleted, and the flag is recorded for replay.
- **Declaration vs. built-in guess:** the declaration replaces the guesses and keeps the facts.
- **A flag or declaration vs. a fact:** no conflict. Tier-3 and tier-4 values accumulate, so `main` survives `--entry-patterns`. Clew's own tests pin this; the `--entry-patterns` collapse was the bug that motivated the rule.
- **Withdrawal:** an empty value (`[]` for a flag, `{}` for a document) is not a statement. It falls through to the declaration and then to the guesses. This is how you undo a recorded flag without deleting the database.
- **Index scope:** the old order (declaration > guard > Doxyfile) no longer holds. Since gh#333 a Doxyfile's `INPUT` is not a scope tier at all. Only a declared `index_scope:` is a decision about the index; otherwise the whole repository is indexed, minus what git ignores. A Doxyfile still supplies `ALIASES`, `PREDEFINED` and filters.
- **Declaration vs. built-in default for a shared-key pattern:** the declaration wins. This was a bug, fixed in the merge that made it match the other surfaces.

**Errors**

- An unknown top-level section in `.clew.yaml` is refused by name. A misspelled key inside `index_scope` is also refused by name.
- A declaration that is present but not a mapping degrades to defaults, per `test_malformed_declaration_degrades_to_defaults`.
- The old `.doxygen-guard.yaml` is no longer read. A repo that has not moved its declaration gets the defaults, with no silent fallback.
- A declared `doxyfile:` must exist when stated, otherwise the build refuses. Other paths are not checked this way.
- `guard:` lives in the same `.clew.yaml`. The gate reads it and the index ignores it.

If you want a starting point, `propose_declaration` drafts a `.clew.yaml` as comments, so committing it changes nothing until you uncomment a section.

Caveat: the index flagged `anchor_mismatch` on `tiers.py` and `_stated_layer`, so the line numbers I could see may be stale. The behaviour described is from the docstrings and tests, not from a fresh read of the source.