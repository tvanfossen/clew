There are three ways to tell clew how to index a repository, and they are ranked by a five-tier rule. Where two statements disagree, the higher tier wins, with one exception for tiers that accumulate.

**The ways to say so**

1. **CLI flags or the structured `options` argument (tier 1, explicit).** This is a one-off override for a single run, such as `--entry-patterns` or `--doxyfile`. MCP callers can now reach it through the `options` argument in `clew/buildoptions.py`.
2. **`.clew.yaml` in the repository root (tier 2, declared).** This is the repository's standing statement of its conventions. Sections use the same names as the CLI options: `index_scope` (roots and excludes), `shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `data_model`, `preprocessor` (predefined macros and `config_header`), `kconfig`, `doxyfile`, `locks`, `requirements`, and others. `clew/declaration.py` lists them as `KNOWN_SECTIONS`. The `guard:` section is also in this file, but the gate reads it, not the index.
3. **Facts the repository already states (tiers 3 and 4).** These are a Doxyfile's ALIASES and PREDEFINED, generator manifests, and language or platform entry points (tier 3). Known-ecosystem signatures such as UDM or ingot are tier 4. clew reads these without being asked, so they are discoverable defaults rather than configuration.
- Tier 5 is the built-in heuristic floor: name-pattern matching, explicitly provisional.

**What happens when they disagree**

The rule is in `clew/tiers.py`: `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`.

- **Stated tiers replace guesses.** A CLI flag or a `.clew.yaml` value replaces the heuristic layer, and a flag replaces the declaration. Tiers 1, 2 and 5 are mutually "replace" in the sense that the highest stated one supplies the value.
- **Tiers 3 and 4 accumulate.** They are unioned in and survive any stated tier. Their label differs, but they behave identically.
- **Facts beat guesses permanently.** Calling a fact a guess would make it discardable, which is why the docstring says "you can correct our guesses; you cannot un-discover a fact." The example it gives: `--entry-patterns` used to drop `main` silently, and the tier rule now guarantees `main` survives.
- **A stated scope persists.** `tests/test_scope_replay.py` checks that a stated `index_scope` survives a later build that states nothing. Build metadata records which declaration was used.
- **Malformed or unknown input.** An unknown section is refused by name, with the spelling checked against `index_scope`. A malformed declaration degrades to defaults (`test_malformed_declaration_degrades_to_defaults`). An `x_`-prefixed experimental section is tolerated and ignored.

**Caveats**

I answered from the index's documentation and test names, not from reading the bodies of `resolve_layered` or `load_declaration`. The tier table and the tests say what the behaviour is meant to be. I did not confirm each code path against that description. Also, the Doxyfile section's exact interaction with `index_scope` (which of INPUT, EXCLUDE and FILE_PATTERNS a stated Doxyfile replaces) is only partly described in the docstrings, so check that before relying on it.