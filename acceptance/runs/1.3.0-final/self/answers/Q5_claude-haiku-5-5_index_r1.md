Clew takes repo-specific indexing conventions from five tiers. Each tier either **replaces** the layer below it or **accumulates** with it, and the resolved set is `(tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. Tiers 1, 2 and 5 are interchangeable "stated" layers, and tiers 3 and 4 always stay in. The rule lives in `clew/tiers.py` (`resolve_layered`, `_stated_layer`).

| Tier | Source | Combines by |
|---|---|---|
| 1 explicit | CLI flag (`--shared-key-patterns`, `--thread-patterns`, `--mqtt-dispatch`, `--data-model`, `--doxyfile`, `--entry-patterns`, `--extra-input`, …) or the `options` argument for embedding callers | replaces the stated layer |
| 2 declared | `<repo>/.clew.yaml`, with the same sections and format as the standalone manifests | replaces the stated layer |
| 3 target-fact | facts the repo already has: Doxyfile ALIASES/PREDEFINED, generator manifests, language/platform entry points | accumulates |
| 4 ecosystem | known-ecosystem signatures (UDM, ingot) | accumulates |
| 5 heuristic | name-pattern guesses, the floor | replaces the stated layer |

The `.clew.yaml` route matters most for MCP callers, because the MCP server passes no CLI flags. `.clew.yaml` is discovered from the repo root that both entry points already receive. `guard:` is read by the doxygen gate, not the indexer. The old `.doxygen-guard.yaml` is no longer read, with no fallback. `clew/declaration.py` rejects unknown top-level keys by name. `propose_declaration` drafts a commented `.clew.yaml` you can review first.

Run mechanics such as `--scope`, `--index-cache` and `--rebuild` are deliberately not declarable. They describe one run, not the repository.

**When two disagree**

- **Flag vs. declaration:** the flag wins for that option. The `.clew.yaml` value is discarded for that run, not merged. `test_explicit_flag_wins_over_the_declaration` pins this.
- **Declaration vs. heuristic:** the declaration wins and the guesses are dropped. Facts from tier 3 and 4 survive, so `main` survives any `--entry-patterns`. Earlier, `--entry-patterns` silently dropped `main` because flags replaced and declarations extended. That was fixed by making both stated tiers replace only tier 5.
- **Empty list:** `explicit=[]` is a withdrawal, not a statement. It falls through to the declaration, then to the guesses. This is how a recorded flag gets undone without deleting the database.
- **Declared pattern vs. built-in default:** the declaration wins. A bug once let the default's accessor class stamp the edge. The test now asserts the outcome, not list order.
- **Scope:** the test docstring gives declaration > `guard` > Doxyfile. A stated `doxyfile:` path must exist. A missing path is an error, not a silent fall-through to whole-repo indexing.
- **Tier 3 vs. tier 4:** these combine identically. Calling a fact an ecosystem signature or the reverse changes the label, not the resolved set.
- **Replay:** only a tier-1 statement is recorded for replay.

One caveat: the index flags `resolve_layered` and `_stated_layer` with `anchor_mismatch`, so the file changed after the index was built. The behaviour above comes from the indexed docs and tests, and I did not re-read the current source to confirm the bodies still match.