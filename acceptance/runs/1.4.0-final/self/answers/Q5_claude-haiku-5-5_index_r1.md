There are four ways to tell clew about a repository, and they combine through one precedence rule. When two disagree, the higher-precedence statement replaces the lower one, except for scope, where clew refuses the conflict outright.

**The four channels, highest precedence first** (`clew/tiers.py`):

| Tier | Channel | Combines by |
|---|---|---|
| 1 | Explicit: CLI flag, or the `options` mapping an embedding caller passes (`clew/buildoptions.py`) | Replaces the lower stated layer |
| 2 | Declared: the repo's `.clew.yaml` | Replaces the guesses |
| 3 | Target facts: things someone else already wrote, such as a Doxyfile's `ALIASES`/`PREDEFINED` or a generator manifest | Accumulates |
| 4 | Ecosystem signatures (UDM, ingot) | Accumulates |
| 5 | Heuristics: name-pattern guesses | Floor; displaced by any stated tier |

The resolved value is `(tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. Facts and ecosystem entries are never discarded. Guesses are discarded as soon as anyone states something.

**Where each channel applies:**

- **CLI flags** (`--scope`, `--doxyfile`, `--requirements`, and so on) are for one run. They are the right tool when you want a one-off override.
- **`.clew.yaml`** is the repo's standing statement. Each section name is also the option name, so a section can be moved verbatim into an `options` mapping. The `guard:` section belongs to the gate, and the index never reads it. Only the `index_scope:` section decides what gets indexed.
- **`options` mapping** is how an MCP or embedding caller states tier 1, since the MCP server passes no CLI flags. It is validated in full before anything is applied, so one bad entry rejects the whole mapping rather than half-applying it.
- **The repo's own Doxyfile** is still used for `ALIASES` and `PREDEFINED`, but its `INPUT` no longer sets scope (gh#333).

**What happens when they disagree:**

1. **Flag vs. `.clew.yaml` for the same layered option:** the flag wins and the declaration is ignored for that option. An empty list passed as a flag (`[]`) is a withdrawal, not a statement, so resolution falls through to the declaration and then to the guesses.
2. **Declaration vs. heuristics:** the declaration wins. Name-pattern guesses are dropped, and facts are kept.
3. **`index_scope` vs. a non-default `--scope`:** clew exits with an error (`_apply_scope` in `clew/cli.py`). A stated `index_scope` is only read under `--scope from-guard`, so silently ignoring it would build a different boundary and report success.
4. **A rejected `index_scope`** (for example, a path outside the repo or one that does not exist) is refused at build time. Internal pipeline callers, which must always get a usable scope, fall back to whole-repo scope and log a warning instead (`clew/scope.py`).
5. **Edits to `.clew.yaml`** are folded into the stage cache key, so a changed declaration cannot reuse stale extractions.
6. **The winning tier is recorded** in `build_meta`, and only tier-1 statements are recorded for replay.

**Two gaps to know about:**

- A repo whose `.clew.yaml` uses a section unknown to the installed clew is refused outright. The refusal names the allowed set but not the likely cause, which is an older clew than the file expects. `tests/test_declaration.py` covers this for `guard:`.
- Duplicate YAML keys are not caught. The repo's own `.clew.yaml` comment records that a duplicated `tags:` key only worked because YAML keeps the last one.

I could not confirm the `propose_declaration` output because its permission was denied in this session. The answer above comes from the source, its docstrings and the index.