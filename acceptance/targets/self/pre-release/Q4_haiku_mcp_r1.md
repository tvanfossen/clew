# Q4 — mcp — haiku — run 1

Perfect. Now I have enough information to answer the question comprehensively. Let me compile my answer based on what I've found:

## Answer

The rule that combines settings supplied in multiple ways is a **five-tier precedence system** with a specific combination rule that treats stated tiers (CLI and declaration) differently from accumulated tiers.

### The Five-Tier Precedence Rule

**Tier precedence (highest to lowest):**
1. **Tier 1 (Explicit)**: CLI flags / direct arguments passed to `build_index()` or `index(action='refresh')`
2. **Tier 2 (Declared)**: The target repository's own `.doxyguard-db.yaml` or `--declare` document
3. **Tier 3 (Target-fact)**: Facts someone else already wrote (Doxyfile ALIASES/PREDEFINED, manifests, language/platform entry points)
4. **Tier 4 (Ecosystem)**: Known-ecosystem signatures (UDM, ingot conventions)
5. **Tier 5 (Heuristic)**: Name-pattern matching (the floor, explicitly provisional)

**The combination rule (dossier:tiers.py:1-4):**

```
resolved = (tier1 or tier2 or tier5) union tier3 union tier4
```

**In plain language:** The resolved value is the **union of three parts**:
- The **stated layer**: whichever of tier 1, tier 2, or tier 5 has a value (in that priority order)
- **PLUS** tier 3 (target-fact) values, which **always accumulate** and cannot be removed by any statement
- **PLUS** tier 4 (ecosystem) values, which **always accumulate**

**Why this matters (dossier:tiers.py:19-23):** You can override the guesses (tier 5), but you cannot remove facts (tiers 3 and 4). Moving a setting from `.doxyguard-db.yaml` to a CLI flag does not accidentally lose other accumulated knowledge. For example, `entry_patterns` declared as `[%trampoline%]` plus the heuristic guesses `[main, app_main]` plus target facts `[app_run]` all combine into the final set `[app_run, main, app_main, %trampoline%]`.

### What an Empty Value on the Command Line Means

**An empty value is a WITHDRAWAL** (dossier:tiers.py:266-271 and dossier:cli.py:764-767):

- **Absent flag** (`None`): Inherits the next tier down (declared, then heuristic)
- **Empty value** (`[]` for lists, `{}` for documents): Explicitly withdraws tier 1, falling back to tier 2 (declaration) and then tier 5 (heuristic)
- **Non-empty value**: Replaces only the heuristic tier, leaving tier-3/4 facts untouched

**Three distinct states** are maintained:

For example, `--exclude` (cli.py:756-796):
- `--exclude` absent → inherits recorded exclusions from previous build
- `--exclude` with no values → withdraws all exclusions, emptying the stated tier
- `--exclude path1 path2` → replaces with these paths

The same pattern applies to all layered options (entry_patterns, shared_key_patterns, etc.).

**Implementation detail (tiers.py:354-358):** Empty sequences are falsy in Python, so `if explicit:` treats both `None` (absent) and `[]` (empty) as "nothing stated," causing both to fall through. The distinction is that `None` means "the flag was absent" while `[]` is explicitly passed and stamped into `build_meta` as a tier-1 statement with no explicit values, creating an auditable record of a withdrawal.

### Why This Matters

This design prevents the silent defect where **a valid setting applied and recorded but not read back gets discarded on the next refresh** (cli.py:757-762). By distinguishing absent (inherit), empty (withdraw), and stated (replace), an operator can:
- Leave a setting alone by omitting the flag
- Explicitly undo a previous statement by passing an empty value
- Override with a new value by passing it

All three outcomes are distinguished, recorded, and replayed consistently across builds.

---

## Gaps

None. The indexing system provided complete documentation of the precedence rule and empty-value semantics through:
- `doxyguard_db/tiers.py` — the formal five-tier combination rule and `resolve_layered()` implementation
- `doxyguard_db/cli.py` — the `_operator_excludes()` function exemplifying the three-state behavior
- `doxyguard_db/buildoptions.py` — tier-1 statement validation

The rule applies uniformly to all layered options: `entry_patterns`, `exclude`, `shared_key_patterns`, `data_model`, `thread_patterns`, `locks`, `mqtt_dispatch`, `dispatch`, `predefined`, `event_tags`, `vendored`, and `requirements`.
