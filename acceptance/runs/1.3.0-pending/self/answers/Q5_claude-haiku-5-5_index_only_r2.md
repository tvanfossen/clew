The index describes several ways to tell clew about a repository, and a fixed rule for when they collide. I answered from the index only, so I haven't checked any of this against the source files.

**The ways to say so**

1. **Built-in defaults.** These apply when nothing is stated. A repository that declares nothing gets them.
2. **`.clew.yaml` at the repo root (tier 2, "declared").** This is the standing, in-tree statement of conventions. Each section takes the same contents as the matching standalone manifest, so a repo can move an existing file's contents in verbatim. The gate reads its own `guard:` section from the same file, and the index ignores that section. Unknown top-level keys are refused by name, except keys with an experimental prefix, which older clew versions tolerate and ignore. A file that holds only comments states nothing, and clew says so in its refusal messages.
3. **CLI flags (tier 1, "explicit").** These are one-off overrides for a single run. Flags are not recorded as declarations.
4. **Structured `options` argument (tier 1, for embedding callers).** This is the MCP and API route. It uses the same vocabulary as `.clew.yaml`, and it is all-or-nothing: if one entry is invalid, nothing is applied.
5. **Facts already written in the target (tier 3).** Examples are a Doxyfile's aliases and predefined macros, a generator manifest, and language or platform entry points.
6. **Known-ecosystem signatures (tier 4).** Examples are UDM and ingot.
7. **Name-pattern heuristics (tier 5).** These are the provisional floor.

**When two disagree**

The combination rule is `resolved = (tier1 or tier2 or tier5) union tier3 union tier4`. In the index's words: "you can correct our guesses; you cannot un-discover a fact."

- **A flag beats the declaration.** Tier 1 and tier 2 each replace the layer beneath them, and the winning tier is recorded. Tests confirm this, for example `test_tier_one_beats_tier_two` and `test_an_explicit_manifest_file_outranks_a_declared_section`.
- **A declaration or flag replaces only the guesses.** A stated value displaces tier 5 but not facts or ecosystem entries. Tests confirm this too, for example `test_an_explicit_statement_displaces_the_guesses_and_keeps_the_facts`.
- **Facts and ecosystem entries always accumulate.** Tiers 3 and 4 survive every stated tier. The index says that an argument over whether something is tier 3 or tier 4 changes only the label, not the resolved set.
- **An empty explicit list is a withdrawal, not a statement.** It falls through to the declaration and then to the guesses. This lets an operator undo a recorded flag without deleting the database.
- **Declared Doxyfile paths** must exist when stated. Otherwise clew would silently fall back to whole-repo synthesis and report success.
- **Scope precedence** is written in the index as "scope's declaration > guard > Doxyfile", where a declaration beats a built-in default.

The index also records that the declaration and the flag do not share one spelling for every option. An older `--entry-patterns` flag used to replace the list while the declaration extended it. That collapse dropped `main` and was silent. The tier rule was introduced to stop this.

**Caveat:** the `resolve_layered` record is marked as anchored to an older version of its file, so its line numbers may be out of date. The behaviour described above comes from its documentation and its tests.