# Q5 — mcp — haiku — run 1

## Q5: Enumerated Fields — Single Source and Guard Mechanism

The enumerated field values are defined in exactly one place: **`doxyguard_db/vocabulary.py`**.

### The Single Source

Every enumerated column in `docs.db` has exactly one `Vocabulary` object defined here. The file holds 37+ distinct vocabularies (line 895–933), each a `Vocabulary` dataclass with:
- A tuple of allowed `values` (ordered and part of the schema text)
- A `rank` dict mapping values to strength/priority
- A `means` docstring explaining the semantics
- Optional `reserved` frozenset for forward-compatible values

### How Duplication is Prevented

**Three mechanisms:**

1. **The `check()` function is the ONLY way to generate CHECK clauses** (line 1030–1040). Every CREATE TABLE statement calls it:
   ```python
   f"CREATE TABLE call_edges (..., source TEXT NOT NULL {check("call_edges", "source")}, ...)"
   ```
   `call_edges.py:269` calls it this way; `reachability.py:67` does the same for `symbol_liveness`.

2. **Filesystem enforcement** (`tests/test_vocabulary.py:96–111`): A test scans every `.py` file in the package and refuses any raw `CHECK(` literal outside `vocabulary.py`. It uses `pathlib.rglob()` rather than git state so untracked files cannot escape — this was documented as how violations landed in this repo before (line 12–14).

3. **The `validated()` method** (line 159–171) is the single choke point for all declared-config paths. It raises `DeclarationError` rather than silently normalizing a typo.

The `COLUMNS` dictionary (line 938–973) is the registry: `(table, column) → Vocabulary`. A test verifies bidirectional consistency between the registry and the shipped schema (line 232–239).

### Dependencies and Why

**Imports only:** `dataclasses`, `pathlib`, `logging.getLogger()` (line 51–54, 59).

**Why it is a leaf:** (line 16–20)
- `_common.py` imports `rich`
- `query/_common.py` is deliberately stdlib-only  
- If this module imported either, one of those layers would become un-importable without the other's dependencies
- Therefore, it is a true leaf with zero intra-package imports

### Merging Identical Entries — What Breaks

**Five vocabularies share the tuple `('low', 'medium', 'high')` and are deliberately five separate objects** (line 22–27):
- `THREAD_STRENGTH` — spawn-detection confidence
- `KEY_STRENGTH` — dataflow edge confidence  
- `LOCK_IDENTITY` — lock identity certainty
- `ACQ_STRENGTH` — acquisition resolution success
- `BOUNDARY_STRENGTH` — external boundary confidence

**If merged into one:**
- Adding a value for one (e.g., adding 'very_high' to `THREAD_STRENGTH`) silently widens the CHECK on all five
- Tests comparing the registry to the shipped schema would still pass because both sides are updated together
- Every CHECK-constrained column would share the same allowed set

**The real failure case** (line 42–45):
- `locks.kind` is part of lock identity: `UNIQUE(name, scope, kind)`
- Two differently-typo'd kinds ("muutex" vs "mutext") normalizing to one token would **COLLAPSE INTO ONE lock row**
- This fabricates shared synchronization between unrelated locks
- The layer's whole premise is that it fails closed against exactly this error

`tests/test_vocabulary.py:387–398` explicitly verifies the five strength objects are distinct (comparing by `id()`).

`file:doxyguard_db/vocabulary.py:22-27,42-45,387-398` `tests/test_vocabulary.py:96-111,387-398`

## Gaps

None. The index answered the complete question.
