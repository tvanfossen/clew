The index gives five ways to say how this repository should be indexed. When they disagree, the tier rules decide, and only some tiers can override others. I answered from docstrings, test names and symbol metadata, not from the bodies of the resolution functions, so treat the merge details as the documented behaviour.

**The ways to say so, highest precedence first** (`clew/tiers.py`):

1. **Explicit call-time options.** `index(action='refresh', ...)` takes `scope`, `exclude`, `doxyfile`, `force` and an `options` mapping. `options` is keyed by the `.clew.yaml` section names, and an unknown key is refused by name. `exclude` is recorded and replayed by later builds.
2. **Declared, in `<repo>/.clew.yaml`.** Each section holds the same contents as the standalone manifest it replaces. Sections include `shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `data_model`, `index_scope`, `doxyfile`, `kconfig`, `preprocessor`, `requirements`, `enrich` and `sub_indexes`. The `guard:` section belongs to the doxygen gate, not the index. If you don't have a file yet, `propose_declaration` drafts one as comments, and `clew export` emits only what was stated.
3. **Target facts someone else wrote.** These are a Doxyfile's ALIASES and PREDEFINED, generator manifests, and language or platform entry points. A Doxyfile's INPUT is not used for scope; it is a documentation target, not a reasoning boundary.
4. **Ecosystem signatures**, such as UDM or ingot.
5. **Heuristics**, which are name-pattern guesses and the explicitly provisional floor.

**When two disagree:**

- **Same setting, flag versus `.clew.yaml`:** the flag replaces the declaration outright. Tests `test_explicit_flag_wins_over_the_declaration` and `test_an_explicit_flag_replaces_the_declaration` confirm this.
- **Stated tiers (1 and 2) versus heuristics (5):** the stated value replaces the guess.
- **Stated tiers versus facts (3 and 4):** facts are never displaced. The documented resolution is `(t1 or t2 or t5) ∪ t3 ∪ t4`, so a Doxyfile alias or an ecosystem entry still adds to a declared value. Tiers 3 and 4 combine identically, so an argument about which of them a fact belongs to changes only the label.
- **Scope:** the declaration's `index_scope` is the only tier that yields index roots. With no declaration the whole repository is indexed, less what git ignores. A rejected declaration refuses the build rather than silently widening it (`test_cli_apply_scope_refuses_a_rejected_declaration`).
- **Doxyfile path:** a stated `doxyfile` must exist. Otherwise resolution would fall back to whole-repo synthesis and report success on the wrong thing.
- **Replay:** the winning tier is stored in `build_meta`. A declaration is re-read on a later build, not replayed from a frozen copy.
- **Ambiguous `scope` name:** the default is documented as `from-declaration`, spelled `from-guard` in recorded builds. The two names refer to the same default.