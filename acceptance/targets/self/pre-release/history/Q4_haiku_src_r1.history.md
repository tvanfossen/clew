# Q4 — src — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll help you find the rule that combines settings from multiple sources. Let me explore the repository.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/self -type f -name "*.py" | head -20
- **got:** ~/ddb-targets/self/acceptance/bench/rescore_audit.py ~/ddb-targets/self/acceptance/bench/fallback_audit.py ~/ddb-targets/self/acceptance/bench/arm_headroom.py ~/ddb-targets/self/acceptance/bench/bench_arms.py ~/ddb-targe…

### 2. `Bash`
- **asked:** command=ls -la ~/ddb-targets/self/ | head -20
- **got:** total 212 drwxrwxr-x 9 tvanfossen tvanfossen  4096 Aug 16 10:30 . drwxrwxr-x 5 tvanfossen tvanfossen  4096 Aug 16 10:30 .. drwxrwxr-x 5 tvanfossen tvanfossen  4096 Aug 16 10:30 acceptance -rw-rw-r-- 1 tvanfossen tvanfoss…

### 3. `Read`
- **asked:** file_path=~/ddb-targets/self/pyproject.toml
- **got:** 1	[build-system] 2	requires = ["hatchling"] 3	build-backend = "hatchling.build" 4	 5	[project] 6	name = "doxyguard-db" 7	version = "0.5.0" 8	description = "Queryable, layered symbol database for C, C++ and Python codebas…

### 4. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db
- **got ⚠ error:** EISDIR: illegal operation on a directory, read '~/ddb-targets/self/doxyguard_db'

### 5. `Bash`
- **asked:** command=ls -la ~/ddb-targets/self/doxyguard_db/
- **got:** total 1588 drwxrwxr-x 5 tvanfossen tvanfossen   4096 Aug 16 10:30 . drwxrwxr-x 9 tvanfossen tvanfossen   4096 Aug 16 10:30 .. -rw-rw-r-- 1 tvanfossen tvanfossen  84806 Aug 16 10:30 ast_symbols.py -rw-rw-r-- 1 tvanfossen …

### 6. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""argparse + pipeline glue for `python -m doxyguard_db`. 3	 4	The pipeline runs in fixed order: 5	  1. doxygen → SQLite + XML 6	  2. copy_database to the user-specified --output path 7…

### 7. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 200	## Same arrangement for the MCP registration doctor: mirrors 201	## `init_command.COMMAND` and is pinned by a test (tests/test_init.py), so a build 202	## invocation never imports it. That matters more here than for …

### 8. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/tiers.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Five-tier precedence for every layered build option — ONE combination rule. 3	 4	`resolved = (tier1 or tier2 or tier5) union tier3 union tier4` 5	 6	In one line: **you can correct ou…

### 9. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/tiers.py
- **got:** 200	    `mqtt_dispatch`. 201	 202	    IT CARRIES NO `values`, deliberately. A manifest's resolved effect is rows in a 203	    dozen tables, computed several frames down inside the loaders; there is no short 204	    value…

### 10. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/buildoptions.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""TIER 1, REACHABLE — one structured `options` argument for an embedding caller. 3	 4	`.doxyguard-db.yaml` is TIER 2 and has been reachable since a declaration became 5	discoverable fr…

### 11. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/tiers.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Five-tier precedence for every layered build option — ONE combination rule. 3	 4	`resolved = (tier1 or tier2 or tier5) union tier3 union tier4` 5	 6	In one line: **you can correct ou…

### 12. `Grep`
- **asked:** pattern=empty.*withdraw|withdrawal|empty list|explicit\s+is a withdrawal, path=~/ddb-targets/self/doxyguard_db
- **got:** ~/ddb-targets/self/doxyguard_db/cli.py:289:## three-state option (absent inherits / empty withdraws / non-empty replaces) into a ~/ddb-targets/self/doxyguard_db/cli.py:290:## two-state one, which is the withdrawal-on-eve…

### 13. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 760	    that is applied and recorded but not read back is discarded by the next refresh, 761	    which then reports success and a healthy coverage ratio over exactly the content 762	    the operator removed. 763	 764	   …

### 14. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/tiers.py
- **got:** 290	 291	## @brief Resolve one layered option: (tier1 or tier2 or tier5) union tier3 union tier4. 292	## @param facts Tier-3 values — facts someone else already wrote. Always present. 293	## @param explicit Tier-1 values…

### 15. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/tiers.py
- **got:** 343	## @version 1 344	## @dg_internal 345	def _stated_layer( 346	    explicit: Sequence[str] | None, 347	    declared: Sequence[str] | None, 348	    heuristics: Iterable[str], 349	) -> tuple[str, tuple[str, ...]]: 350	  …

### 16. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 410	    parser.add_argument( 411	        "--exclude", 412	        nargs="*", 413	        default=None, 414	        metavar="PATH", 415	        help=( 416	            "Repo-relative paths to leave OUT of the index. An --e…

### 17. `Bash`
- **asked:** command=grep -n "entry-patterns\|entry_patterns" ~/ddb-targets/self/doxyguard_db/cli.py | head -30
- **got:** 226:OPTION_ENTRY_PATTERNS = "entry_patterns" 229:## NOT replayed: unlike `--entry-patterns` there is no flag carrying the prefixes 301:##   * `predefined`, `entry_patterns`, `shared_key_patterns`, `data_model`, `thread_p…

### 18. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 1618	        output, 1619	        entry_patterns=list(entry_seeds.values), 1620	        extra_seeds=python_entry_seeds(output, repo_root, cache), 1621	    ) 1622	    timer.mark("reachability") 1623	 1624	    # Stamp the …

### 19. `Bash`
- **asked:** command=grep -B5 -A5 "add_argument.*entry.patterns" ~/ddb-targets/self/doxyguard_db/cli.py
- **got:** (Bash completed with no output)

### 20. `Bash`
- **asked:** command=grep -n "def build_index\|def index" ~/ddb-targets/self/doxyguard_db/cli.py | head -20
- **got:** 2147:def build_index(

### 21. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/cli.py
- **got:** 2147	def build_index( 2148	    output: Path | str, 2149	    repo_root: Path | str | None = None, 2150	    doxyfile: Path | str | None = None, 2151	    scope: str | None = None, 2152	    declare: str | Path | None = None,…

### 22. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/tiers.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Five-tier precedence for every layered build option — ONE combination rule. 3	 4	`resolved = (tier1 or tier2 or tier5) union tier3 union tier4` 5	 6	In one line: **you can correct ou…

**Reasoning.** Now I have the complete picture. Let me provide the answer.

## ANSWER

**The Rule: Five-Tier Precedence for Layered Settings**

The program combines settings from multiple sources using a single rule stated in `tiers.py:4`:

```
resolved = (tier1 or tier2 or tier5) union tier3 union tier4
```

This breaks down as:

| Tier | Source | Behavior | Priority |
|------|--------|----------|----------|
| 1 | Explicit (CLI flag) | REPLACES the stated layer | Highest |
| 2 | Declared (`.doxyguard-db.yaml`) | REPLACES the stated layer | Second |
| 3 | Target-fact (discovered facts) | ACCUMULATES | Always

---

## Final answer as submitted

Now I have the complete picture. Let me provide the answer.

## ANSWER

**The Rule: Five-Tier Precedence for Layered Settings**

The program combines settings from multiple sources using a single rule stated in `tiers.py:4`:

```
resolved = (tier1 or tier2 or tier5) union tier3 union tier4
```

This breaks down as:

| Tier | Source | Behavior | Priority |
|------|--------|----------|----------|
| 1 | Explicit (CLI flag) | REPLACES the stated layer | Highest |
| 2 | Declared (`.doxyguard-db.yaml`) | REPLACES the stated layer | Second |
| 3 | Target-fact (discovered facts) | ACCUMULATES | Always present |
| 4 | Ecosystem (known signatures) | ACCUMULATES | Always present |
| 5 | Heuristic (name-pattern guesses) | REPLACES the stated layer | Floor (default) |

**The Precise Rule:** Pick the highest-priority non-empty tier from (1, 2, 5), then union it with tiers 3 and 4, then de-duplicate while preserving first-seen order.

**In Code Form** (`tiers.py:330-335`):
```python
tier, stated = _stated_layer(explicit, declared, heuristics)
return LayeredResolution(
    values=_ordered_unique((*facts, *ecosystem, *stated)),
    tier=tier,
    stated=stated,
)
```

Where `_stated_layer` (lines 345-358) checks:
```python
if explicit:
    return TIER_EXPLICIT, tuple(str(v) for v in explicit)
if declared:
    return TIER_DECLARED, tuple(str(v) for v in declared)
return TIER_HEURISTIC, tuple(heuristics)
```

**The Motto** (`tiers.py:6`): "You can correct our guesses; you cannot un-discover a fact."

---

## **Empty Value on the Command Line**

An empty value means **withdrawal**, not absence. The program maintains **three states**:

1. **Absent** (`None`): The flag is not passed → **inherits** whatever was previously recorded
2. **Empty** (`[]`): The flag is passed with no values (e.g., `--exclude` with nothing after) → **withdraws** any tier-1 statement, falling back to tier 2 or tier 5
3. **Non-empty**: The flag is passed with values → **replaces** the previous tier-1 statement

**Example from cli.py:414-419** (the `--exclude` help text):
> "Pass --exclude with no values to withdraw a recorded one; omit the flag entirely to inherit it."

This three-state distinction is critical (`cli.py:764-767`):
> "THREE STATES, kept distinct: the flag ABSENT (`None`) inherits, the flag EMPTY (`[]`) withdraws, and a non-empty list replaces. Collapsing absent into empty would make the record unreadable-back; collapsing empty into absent would make it unwithdrawable except by deleting the database."

The empty list is **recorded** as a tier-1 statement (marking that the operator made a decision) but is **falsy**, so it doesn't win the comparison — it falls through to declared or heuristic, allowing withdrawal without database deletion.

---

## Gaps

None. The rule is explicit and uniformly documented. Every path through which a setting can arrive (`cli.py`, `tiers.py`, `buildoptions.py`) references the same five-tier rule and the three-state handling.
