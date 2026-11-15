Clew has three layers of configuration, and they resolve by a fixed precedence. Before I list them, note that I read the precedence rule from the code's own documentation (`clew/tiers.py`, `clew/cli.py`, `clew/requirements.py`) and did not run a build to confirm it.

**The ways to say so**

| Tier | Channel | Notes |
|---|---|---|
| 1 | CLI flags, e.g. `--shared-key-patterns`, `--thread-patterns`, `--mqtt-dispatch`, `--data-model`, `--requirements`, `--entry-patterns` | One-off. The MCP server passes none of these. |
| 1 | Inline document via `--declare`, or the structured `options` argument for embedding callers | Same validation as a file. An empty one counts as "no statement". |
| 2 | `.clew.yaml` at the repo root | The standing declaration, reached by both CLI and MCP. Sections mirror the standalone manifest formats. The `guard:` section belongs to the gate, and the index ignores it. |
| 3 | Facts the target already states: its Doxyfile (`ALIASES`, `PREDEFINED`, `INPUT`), generator manifests, language and platform entry points | Accumulate. Nothing stated can remove them. |
| 4 | Known-ecosystem signatures, e.g. UDM or ingot | Accumulate, like tier 3. |
| 5 | Built-in name-shape guesses | The floor. Any stated value replaces them. |

Legacy `.doxygen-guard.yaml` and its `x-clew` passthrough are no longer read. A repo still carrying one gets the defaults with no fallback.

**When two disagree**

- **Flag vs `.clew.yaml`:** the flag wins, and it replaces the declared value for that option as a whole. It does not merge. Under the current rule, a stated value displaces only the tier-5 guesses, so a repo's own `entry_patterns` no longer drops `main`.
- **Declaration vs convention (requirements catalog):** the order is flag, then declaration, then conventional file (`requirements.yaml` at the root, or under `docs/`), then nothing. If two conventional catalogs exist, clew logs a warning and picks the first.
- **Scope:** a declaration beats the gate's config, which beats the Doxyfile's `INPUT`.
- **Stated value vs tier 3 or 4 fact:** both apply. The fact is never discarded. Tiers 3 and 4 combine the same way; only the label differs.
- **Winner visibility:** the tier that supplied each option is recorded in `build_meta`. The refusal and status messages also say whether `.clew.yaml` was honoured.

**Malformed input**

- An unknown section name is refused with an error that names the problem.
- An unreadable file, or one that is not a mapping, is ignored with a message, and defaults apply.
- A file with only comments is treated as stating nothing, and the message says so.