Clew has three ways to tell it how to index a repo, and when they conflict, the more explicit one wins. The rule is "you can correct our guesses; you cannot un-discover a fact."

**The ways to say so**

1. **CLI flags / tool arguments (tier 1, "explicit").** These cover one build. The `index(action='refresh')` call takes `options`, `scope`, `exclude`, `doxyfile` and `sub_index`, and `clew` accepts argv flags such as `--entry-patterns`.
2. **`.clew.yaml` at the repo root (tier 2, "declared").** This is the repo's standing declaration. It has named sections (for example `dispatch:`, `locks:`, `threads:`, `entry_patterns:`, `mqtt:`, `shared_key:`, `data_model:`, `preprocessor:`, `kconfig:`), and `clew/declaration.py` lists every accepted key in `ACCEPTED_SECTIONS`. A `guard:` section is also allowed in the same file; that section configures the doxygen-guard gate, and the index ignores it. An unknown top-level key is refused by name, and an unreadable or non-mapping file falls back to defaults.
3. **Facts the target already wrote (tier 3, "target-fact").** Examples are a Doxyfile's `ALIASES`/`PREDEFINED`, a generator manifest, and language or platform entry points. These are read automatically.
4. **Known-ecosystem signatures (tier 4).** Examples are UDM and ingot. These are also automatic.
5. **Built-in name-pattern heuristics (tier 5).** These are the floor, and they are explicitly provisional.

Scope is resolved separately. A declared scope overrides the Doxyfile's INPUT; the docstring in `clew/scope.py` (around line 462) says the declaration beats the guard and the Doxyfile. I read that from the docstring and did not trace the full code path.

**When two of them disagree**

- **Tiers 1 and 2 (flag over declaration).** The flag replaces the declared value for that build. The `options` in `build_meta` record which tier won.
- **Tiers 1, 2 and 5 (stated over heuristic).** A stated value replaces the tier-5 guesses. The `entry_patterns` tests confirm this: a stated value replaces guesses but keeps built-in facts such as `main`.
- **Tiers 3 and 4 (facts).** These accumulate. No flag or declaration removes them. The resolved set is the union of the stated-or-guessed layer with the facts, so a fact cannot be discarded by stating something else.
- **Declaration over built-in default.** A declared pattern beats a default with the same prefix. The tests in `tests/test_build_docs_db.py` cover a case that used to be backwards and was fixed.

The result is that a flag does not silently drop a declared value, and a declaration does not silently drop a fact from a Doxyfile or manifest. The tier that won is recorded in the build log and `build_meta`, so you can see which layer applied.

I did not run `propose_declaration` because its permission was not granted. That tool would show what the defaults would find for a repo that has no `.clew.yaml`.