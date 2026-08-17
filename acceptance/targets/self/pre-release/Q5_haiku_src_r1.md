# Q5 — src — haiku — run 1

## Answer

### **Location: ONE Definition at `doxyguard_db/vocabulary.py:1–81`**

The enumerated field values are defined exactly once in `vocabulary.py` as `Vocabulary` objects (dataclass instances). Each `Vocabulary` carries:
- `id`: The column identifier  
- `values`: A **tuple** of allowed member strings (order is part of the schema)  
- `means`: Documentation of what the vocabulary means  
- `rank`: A **dict** mapping each value to its precedence (used for collapsing, ranking, choosing strongest edges)  
- `reserved`: A frozenset of values the CHECK permits but no code path writes (forward-compatibility flag)

Examples from the file:

- `KEY_STRENGTH` (line 280–286): `values=("low", "medium", "high")` for shared-key dataflow edge confidence  
- `THREAD_STRENGTH` (line 361–367): `values=("low", "medium", "high")` for thread spawn detection confidence  
- `LOCK_IDENTITY` (line 387–392): `values=("low", "medium", "high")` for lock-identity resolution certainty  
- `ACQ_STRENGTH` (line 424–429): `values=("low", "medium", "high")` for acquisition-extent resolution confidence  
- `BOUNDARY_STRENGTH` (line 508–514): `values=("low", "medium", "high")` for external-boundary terminus confidence

---

### **How the Codebase Avoids Restating Values**

Two mechanisms prevent duplication:

**1. Schema generation via `check()` method** (line 129–138)  
Instead of spelling CHECK clauses as string literals at CREATE TABLE sites, the `check(table, column)` function (line 1030–1040) looks up the vocabulary from the `COLUMNS` dict (line 938–973) and calls `.check(column)` to generate it:

```python
# In locks.py CREATE TABLE:
kind TEXT NOT NULL {check("locks", "kind")},
# Expands to:
# CHECK(kind IN ('mutex', 'recursive_mutex', 'shared_mutex', 'semaphore', 'spinlock', 'unknown'))
```

The `COLUMNS` dict (line 938–973) maps `(table_name, column_name)` tuples to their vocabularies:  
`("locks", "kind"): LOCK_KIND` — the table, column and their vocabulary are bound in ONE place.

**2. Declared-config validation via `.validated(value, *, owner, field)`** (line 159–171)  
When a repo's `.doxyguard-db.yaml` declares a value for an enumerated field (e.g., a lock pattern's `form`), the loader calls `vocabulary.validated()` on that value. If the value is not in `vocabulary.values`, it raises `DeclarationError` with the allowed set and the origin file:

```python
# In locks.py, reading a declared lock pattern:
form=ACQ_FORM.validated(str(entry.get("form", "raii")), owner=owner, field="form"),
```

This is the same vocabulary instance that generated the CHECK clause, so the two cannot disagree.

---

### **Dependencies and Why**

`vocabulary.py` is a **"TRUE LEAF"** (line 16). It has **zero intra-package imports** by design (line 16–20):

- `doxyguard_db/_common.py` imports `rich` (terminal rendering)  
- `doxyguard_db/query/_common.py` is deliberately stdlib-only (to stay lightweight)  
- Importing either here would entangle both their dependencies into every importer of `vocabulary.py`

The logger is imported directly from `logging` (not from `._common`), and the file documents that it "logs nothing on purpose — a pure registry has nothing to report, since validation RAISES and generation is deterministic" (line 56–60).

**Why this matters:** Every other module can import from `vocabulary` without pulling in `rich` or complex query dependencies. The vocabulary is a stable, minimal foundation that the entire schema and validation layer rests on.

---

### **What Breaks if Two Identical-Looking Entries Merge**

**Five vocabularies share the identical tuple `("low", "medium", "high")`** (line 22–27):

1. `KEY_STRENGTH` (line 280) — confidence that a shared-key write/read pair is real dataflow  
2. `THREAD_STRENGTH` (line 361) — confidence that a spawn site's entry function was identified correctly  
3. `LOCK_IDENTITY` (line 387) — certainty that two acquisitions take the **same** lock  
4. `ACQ_STRENGTH` (line 424) — confidence that an acquisition's critical-section extent was resolved  
5. `BOUNDARY_STRENGTH` (line 508) — confidence that an external boundary is real, not a missed resolution  

**They are FIVE DISTINCT OBJECTS because they mean five different things.**

Each maps to a different table and column:

| Vocabulary | Table | Column | Meaning |
|---|---|---|---|
| `KEY_STRENGTH` | `shared_key_edges` | `confidence` | Is this dataflow seam real? |
| `THREAD_STRENGTH` | `threads` | `confidence` | Did we identify the spawned function correctly? |
| `LOCK_IDENTITY` | `locks` | `identity_confidence` | Do two uses refer to the **same** lock? |
| `ACQ_STRENGTH` | `lock_acquisitions` | `confidence` | How far does the critical section extend? |
| `BOUNDARY_STRENGTH` | `external_boundaries` | `confidence` | Is this call truly external? |

**If someone merged them into ONE object:**

```python
# WRONG — a single object bound to five different columns
STRENGTH = Vocabulary(id="strength", values=("low", "medium", "high"), ...)
COLUMNS = {
    ("shared_key_edges", "confidence"): STRENGTH,      # ← same object
    ("threads", "confidence"): STRENGTH,               # ← same object
    ("locks", "identity_confidence"): STRENGTH,        # ← same object
    ("lock_acquisitions", "confidence"): STRENGTH,     # ← same object
    ("external_boundaries", "confidence"): STRENGTH,   # ← same object
}
```

**Silent, undetectable breakage:**

1. **Adding a value to one silently widens the CHECK on all five** — If someone added a sixth strength level `"ultra_high"` to support boundary analysis, all five tables would suddenly allow it in columns where it makes no semantic sense.

2. **Tests stay green** — The test that "the shipped schema matches the vocabulary registry" would pass (line 937: "the ONLY way a CREATE TABLE gets an enumerated clause"), because the registry and schema would still agree. But the behavior would now be broken.

3. **Declarative config validation becomes ambiguous** — When parsing `.doxyguard-db.yaml`, a typo like `strength: "mediumm"` would fail identically for all five uses, but the user wouldn't know whether they're editing a lock pattern, a shared-key declaration, or a boundary hint. The error message would have to say "invalid strength" rather than "invalid thread spawn confidence" — losing specificity.

4. **Rank inconsistency silently breaks** — Different use cases may want different rank orderings. For example, in reachability analysis, a "fuzzy" confidence might still contribute. But merging them means changing one vocabulary's rank ordering changes all five, potentially breaking seeding logic for unrelated layers.

The file documents this (line 22–27):

> "Binding one object to all five would mean that adding a value for one silently widens the CHECK on the other four, while every test that compares the shipped schema to this registry stays green."

This is why `vocabulary.py` enforces strict **one-definition-per-meaning**, not one-definition-per-shape. The identical tuple is intentional and the five separate objects prevent exactly the class of bug (value drift across different columns) that the module was created to prevent.

---

## Gaps

None. The definition location, mechanism, dependencies, and breaking case are all clearly documented in the source file itself and demonstrated through the actual usage pattern in the codebase.
