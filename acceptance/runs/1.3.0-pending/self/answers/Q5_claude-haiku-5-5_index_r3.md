Clew has four ways to tell it a repository's indexing conventions, and they sit in a fixed precedence. When two disagree, the higher one wins, and the loser is not silently dropped in every case.

**The ways to say so, highest precedence first**

| Tier | Source | How it combines |
|---|---|---|
| 1 | Explicit statement: a CLI flag, or the `options` argument on the MCP `index` tool, keyed by `.clew.yaml` section name | Replaces the stated layer |
| 2 | Repo's `.clew.yaml` (repo root only) | Replaces the stated layer |
| 3 | Facts someone else wrote: a Doxyfile's `ALIASES`/`PREDEFINED`, a generator manifest, a language entry point | Accumulates |
| 4 | Known-ecosystem signature (e.g. UDM, ingot) | Accumulates |
| 5 | Name-pattern heuristics, the built-in floor | Replaced by any stated tier |

The rule is in `clew/tiers.py` (`resolve_layered`, `resolve_document`): the resolved set is `(tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. The module docstring summarises it as "you can correct our guesses; you cannot un-discover a fact." Tiers 3 and 4 behave identically; the distinction is only the label.

**Index scope is a special case.** Only the repo's own `index_scope:` section in `.clew.yaml` yields roots. The Doxyfile's `INPUT` is no longer a tier (gh#333): the Doxyfile is still used for `ALIASES` and `PREDEFINED`, but its `INPUT` is replaced. With no declaration, the scope is the whole repo minus what git ignores (`clew/scope.py`).

**The `.clew.yaml` file itself**

- Absent is normal. The file is read only from the repo root.
- Malformed YAML is logged at WARNING and treated as absent, so the build degrades to defaults.
- An unknown top-level section is refused (`DeclarationError`), because a misspelled section would otherwise be ignored while the build reports it was honoured. Sections prefixed with the experimental prefix are tolerated and ignored, with a warning.
- The `guard:` section belongs to the gate. The index reads it too, for the `@req` pattern and requirements catalogue, but at a lower severity: the gate refuses an invalid section, while the index warns and uses permissive defaults (`clew/guardconfig.py`).

**When they disagree**

- **Flag vs. declaration:** the flag wins outright. `_declared_or_flag` in `clew/cli.py` returns the stated value and never merges it with the declared one. The declared value is not discarded; it is still there when the flag is absent.
- **Empty values are withdrawals, not statements.** An empty explicit list or an empty document (`[]` or `{}`) falls through to the declaration and then to the floor. That is how an operator undoes a recorded flag without deleting the database.
- **Stated vs. recorded:** only a tier-1 statement is written to the database for replay. A declaration is re-read on each build rather than frozen, so editing the file takes effect on the next build.
- **Rejected `index_scope`:** for internal pipeline callers, `derive_scope` absorbs a rejected declaration into the whole-repo tier and logs a warning. The CLI and MCP refresh path call `declared_scope_rejection` first and refuse the build instead. This was the fix for an excludes-only declaration that let a build walk a vendored tree and time out.
- **Tier 1 vs. tier 3/4/5:** tier-1 values displace only the replaceable layer (tiers 2 and 5). Facts from tiers 3 and 4 still accumulate, so a stated `--entry-patterns` cannot drop `main`.

**Helpers.** `clew propose` (`propose_declaration`) drafts a `.clew.yaml` as comments, and `clew export` writes tier-1 statements back out as a declaration.

I did not check the CLI's full flag list against the docs, so the tier-1 list above is the set the code paths and tests name, not a complete enumeration of every flag.