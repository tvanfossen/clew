Clew has four ways to take a repo's conventions, and a fixed precedence for when they conflict. The rule comes from `clew/tiers.py`, and the scope rule from `clew/scope.py`.

**The ways to say so**

| Route | Tier | Notes |
|---|---|---|
| CLI flag, or the `options` argument for an embedding caller (`clew/buildoptions.py`) | 1, explicit | One build only. Replays on a later build only when it was stated as a flag. |
| `.clew.yaml` at the repo root | 2, declared | The standing, checked-in declaration. `propose_declaration` drafts one as comments. |
| Doxyfile `ALIASES` / `PREDEFINED` | 3, target-fact | Read for facts only. Its `INPUT` no longer sets scope (gh#333). |
| Known-ecosystem signatures (UDM, ingot) | 4, ecosystem | Built in. |
| Name-pattern guesses | 5, heuristic | The floor, explicitly provisional. |

The `index` tool's `scope`, `exclude` and `options` parameters also reach this layer. `exclude` is recorded and replayed by later builds.

**What happens when they disagree**

The combination rule is `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. The short version is "you can correct our guesses; you cannot un-discover a fact."

- **Flag and declaration on the same option:** the flag wins outright. The declaration is not merged in. An empty flag (`[]`) is a withdrawal and falls through to the declaration.
- **Declaration and guesses:** the declaration replaces the heuristic layer.
- **Facts and ecosystem (tiers 3 and 4):** these accumulate and no stated tier removes them. A declaration cannot delete a Doxyfile-supplied alias or predefine.
- **Empty document:** `{}` is also a withdrawal. It falls through to the floor, and nothing is recorded.
- **Scope:** the declared `index_scope:` wins over the whole-repo default. The Doxyfile `INPUT` is no longer a scope tier. I did not verify how an explicit `scope` argument interacts with a declared `index_scope:`, so check that before relying on it.

**Errors and visibility**

- An unknown top-level section in `.clew.yaml` is refused by name, and the whole declaration is rejected rather than applied partially. Malformed YAML degrades to defaults. `guard:` belongs to doxygen-guard and is ignored by the index.
- The winning tier for each layered option is stored in `build_meta` and surfaced by `_options_meta`, so you can see which tier chose a setting.