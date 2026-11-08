**The ways to say so, strongest first:**

| Way | Where | Tier | Notes |
|---|---|---|---|
| CLI flag (`--shared-key-patterns`, `--entry-patterns`, `--doxyfile`, …) | command line | 1 (explicit) | One-off override. Not reachable from the MCP server before this was fixed. |
| `options` argument | embedding caller, `build_index` / `apply_options` | 1 (explicit) | The same settings as the declaration file, passed as a structured mapping. Validated as a whole before any value is applied, so a bad entry changes nothing. |
| `.clew.yaml` in the repo root | repo | 2 (declared) | The standing statement for the repo. Both CLI and MCP read it, because both already know the repo root. |
| Facts the repo already wrote (a Doxyfile's ALIASES/PREDEFINED, a generator manifest, a language or platform entry point) | repo | 3 (target-fact) | Read automatically. |
| Known-ecosystem signatures (UDM, ingot) | automatic | 4 (ecosystem) | Read automatically. |
| Name-pattern guesses | automatic | 5 (heuristic) | The floor. Explicitly provisional. |

Two related points:
- `.clew.yaml` has one section per setting, with the same format as the standalone manifest. A repo can move an existing manifest's contents in unchanged.
- The `guard:` section belongs to the doxygen-guard gate, not the index. The index ignores it. The old `.doxygen-guard.yaml` is no longer read at all.
- Build mechanics such as `--scope`, `--index-cache` and `--rebuild` are per-run choices and have no declaration form.

**When two disagree:**

The resolution rule is `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`.

- **A CLI flag or `options` value beats the declaration.** It replaces the declaration's values, not adds to them. The file is the standing statement and the flag is a deliberate one-off override.
- **The declaration beats the guesses.** It replaces tier 5 only.
- **Facts (tier 3) and ecosystem signatures (tier 4) are never displaced.** They accumulate beneath any stated value. So passing `--entry-patterns` does not drop `main`. The stated tier can only correct guesses; it cannot un-discover a fact.
- **An empty explicit list is a withdrawal, not a statement.** `[]` falls through to the declaration, then to the guesses. That lets an operator undo a recorded flag without deleting the database.
- **The winning tier is recorded** in `build_meta`. Only tier-1 statements are recorded for replay.
- **For scope**, the declaration beats the guard config, which beats the Doxyfile's INPUT. A Doxyfile's INPUT, EXCLUDE and FILE_PATTERNS are replaced by a declared scope.

**Failure modes:**
- A malformed `.clew.yaml` is ignored and built-in defaults apply. The refusal message names the file and says it was ignored.
- A `.clew.yaml` with only comments is treated as stating nothing, and the message says so.
- A declared `doxyfile:` must exist. A missing one is refused rather than silently falling back to whole-repo indexing.
- `propose_declaration` drafts a commented `.clew.yaml` to review and never overwrites an existing one without force.

One caveat: the index flagged `resolve_layered` with an anchor mismatch, so its line numbers may be stale. The rules above come from the module documentation and the precedence tests, not from a live read of the code.