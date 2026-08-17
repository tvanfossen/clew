# Q4 — src — haiku — run 1

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
