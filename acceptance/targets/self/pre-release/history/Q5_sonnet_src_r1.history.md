# Q5 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/self -iname "*vocabulary*"
- **got:** ~/ddb-targets/self/doxyguard_db/vocabulary.py ~/ddb-targets/self/tests/data/schema_vocabulary.json ~/ddb-targets/self/tests/test_vocabulary.py

### 2. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/vocabulary.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""The schema's enumerated vocabularies — ONE definition per value set. 3	 4	Every enumerated column in docs.db used to spell its allowed values as a SQL 5	string literal at the CREATE …

### 3. `Read`
- **asked:** file_path=~/ddb-targets/self/tests/test_vocabulary.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Tests for the central schema vocabulary (doxyguard_db.vocabulary). 3	 4	Three distinct jobs, and the first is the one that matters most: 5	 6	  1. A FILESYSTEM SOURCE SCAN forbidding…

### 4. `Grep`
- **asked:** pattern=UNIQUE\(name, scope, kind\)|UNIQUE.*kind, path=~/ddb-targets/self/doxyguard_db
- **got:** ~/ddb-targets/self/doxyguard_db/threads.py:397:            UNIQUE(name, entry_memberdef_rowid, kind) ~/ddb-targets/self/doxyguard_db/locks.py:215:    (`UNIQUE(name, scope, kind)`), so two differently-typo'd kinds normali…

### 5. `Read`
- **asked:** __unparsedToolInput
- **got ⚠ error:** <tool_use_error>InputValidationError: Read was called with input that could not be parsed as JSON. You sent (first 92 of 92 bytes): {"file_path": "~/ddb-targets/self/doxyguard_db/locks.py", "offset": 195, 330} Common cau…

### 6. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/locks.py
- **got:** 195	def load_lock_patterns(source: Path | dict | None) -> list[LockPattern]: 196	    """Expected shape, mirroring the thread/accessor manifests:: 197	 198	        locks: 199	          - name: "ScopedLock"       # a proje…

### 7. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/query/models.py
- **got:** 495	    ## One site to go and read. Chosen as the first RESOLVED site when the pair has one, 496	    ## so the exemplar is the strongest evidence rather than an arbitrary row. 497	    via: str 498	    holder: str 499	   …

**Reasoning.** I have what I need to answer.

## Answer

**The single source of truth is `doxyguard_db/vocabulary.py`.** Every enumerated column's allowed value set lives exactly once there, as a `Vocabulary` dataclass instance (`doxyguard_db/vocabulary.py:100-171`), collected into a registry keyed by `(table, column)`:

```
COLUMNS: dict[tuple[str, str], Vocabulary]   # vocabulary.py:938-973
```

Two functions are the only sanctioned way to turn a `Vocabulary` into SQL or to accept a declared string:
- `Vocabulary.check(column)` (`vocabulary.py:129-138`) generates the SQL `CHECK(col IN (...))` clause by exp

---

## Final answer as submitted

I have what I need to answer.

## Answer

**The single source of truth is `doxyguard_db/vocabulary.py`.** Every enumerated column's allowed value set lives exactly once there, as a `Vocabulary` dataclass instance (`doxyguard_db/vocabulary.py:100-171`), collected into a registry keyed by `(table, column)`:

```
COLUMNS: dict[tuple[str, str], Vocabulary]   # vocabulary.py:938-973
```

Two functions are the only sanctioned way to turn a `Vocabulary` into SQL or to accept a declared string:
- `Vocabulary.check(column)` (`vocabulary.py:129-138`) generates the SQL `CHECK(col IN (...))` clause by explicit quote-and-join (never `{tuple!r}`, which mis-handles a 1-value tuple or an apostrophe — `vocabulary.py:29-36`).
- `Vocabulary.validated(value, owner=, field=)` (`vocabulary.py:159-171`) is the "single choke point every declared-enum path routes through" — it returns the value unchanged if it's a member, else raises `DeclarationError` (`vocabulary.py:63-76`) naming the origin file, the bad token, and the full allowed set.

**How the rest of the codebase is kept from restating the values:**
1. **DDL callers never spell a value list.** Every `CREATE TABLE` that needs a CHECK calls the module-level `check(table, column)` (`vocabulary.py:1030-1040`), e.g. `locks.py:320,323-324`: `` kind TEXT NOT NULL {check("locks", "kind")} ``. `check()` raises `KeyError` for an unregistered column rather than silently omitting the CHECK.
2. **A filesystem source scan is the actual gate**, in `tests/test_vocabulary.py:96-111` (`test_no_raw_check_literal_survives_outside_vocabulary`): it `rglob`s every `.py` file in the package and fails if the literal string `"CHECK("` appears anywhere except `vocabulary.py`. It deliberately scans the filesystem, not `git ls-files`, because an untracked file already slipped a raw `CHECK(` past `pre-commit --all-files` once (`htmlview.py`, per the docstring at lines 6-14 and the project CLAUDE.md's "GATE TRAP" note).
3. **A second scan forbids reintroducing a parallel constant** (`test_no_module_redefines_a_valid_constant`, `test_vocabulary.py:124-142`): no module may define a `_VALID_*` constant, which is exactly the shape of the historical bug (`_VALID_KINDS` defined twice, once in `threads.py`, once in `locks.py`, with different values — `vocabulary.py:6-10`).
4. **Declared-config loaders route through `.validated()`**, not string comparison — e.g. `locks.py:254-260` (`_declared_lock_pattern`) validates `form`, `kind`, `mode`, `role` against `ACQ_FORM`/`LOCK_KIND`/`ACQ_MODE`/`ACQ_ROLE` respectively, so a `.doxyguard-db.yaml` typo raises `DeclarationError` at load time instead of being coerced to a default (documented failure mode at `locks.py:206-217`: `form: "cal"` used to silently become an RAII guard).
5. **A committed golden snapshot** (`tests/data/schema_vocabulary.json`, compared in `test_shipped_schema_matches_the_committed_snapshot`, `test_vocabulary.py:225-229`) catches a *widening* of a vocabulary, which a registry-vs-registry check can't (`test_vocabulary.py:16-20`).
6. **A cache-stage scan** (`test_cache_stage_names_are_not_spelled_inline`, `test_vocabulary.py:145-156`) additionally forbids inlining the `extract_cache.stage` literal, since that column carries no CHECK at all (`vocabulary.py:565-570`).

**Dependencies, and why they're what they are:**
- `dataclasses`, `pathlib` only (`vocabulary.py:53-54`). The module docstring calls this out explicitly as a **TRUE LEAF** with **zero intra-package imports, by design** (`vocabulary.py:16-20`): `doxyguard_db/_common.py` pulls in `rich`, and `doxyguard_db/query/_common.py` is deliberately stdlib-only — importing either here would make one of those two layers un-importable without the other's dependencies. Even logging is avoided: the module logs nothing on purpose since validation raises and generation is deterministic (`vocabulary.py:56-60`).

**What breaks if two vocabulary entries with identical-looking values were merged into one object:**
The module docstring states this directly (`vocabulary.py:22-27`): five distinct vocabularies — `THREAD_STRENGTH`, `KEY_STRENGTH`, `LOCK_IDENTITY`, `ACQ_STRENGTH`, `BOUNDARY_STRENGTH` — all share the tuple `('low','medium','high')` but mean five unrelated things (spawn-detection strength, dataflow-seam confidence, lock-identity certainty, critical-section-resolution confidence, external-boundary confidence). If two of these were collapsed into one shared `Vocabulary` object, **adding a value for one purpose would silently widen the CHECK constraint on all the others that share the object**, and — critically — "every test that compares the shipped schema to this registry stays green," because the registry-vs-shipped-schema reconcile test (`test_reconcile_is_bidirectional_and_unfiltered`, `test_vocabulary.py:232-239`) only checks that registered and shipped columns agree, not that distinct meanings stay distinct. This exact invariant is pinned by `test_the_five_strength_vocabularies_are_distinct_objects` (`test_vocabulary.py:387-398`), which asserts `len({id(v) for v in five}) == 5` — i.e., it specifically checks object identity, not just value equality, precisely to catch this merge.

A more severe case is `LOCK_KIND` specifically (`vocabulary.py:377-385`, and the docstring warning at `vocabulary.py:41-45`): `locks.kind` is part of the `locks` table's identity key, `UNIQUE(name, scope, kind)` (`locks.py:325`, `query/models.py:510-511`). If two lock-kind entries that "look identical" (e.g. a typo variant) were merged/normalized to one token, "two differently-typo'd kinds normalizing to one token merge unrelated acquisitions into a single lock row" — fabricating a shared lock between two acquisition sites that never actually contend for the same mutex. This is exactly why `validated()` fails closed rather than normalizing to an `'unknown'` fallback (`vocabulary.py:38-45`): there is no honest fallback value that doesn't invent a specific, false synchronization claim.

## Gaps

- I did not exhaustively trace every one of the ~30 call sites of `check()`/`bool_check()`/`.validated()` across the pipeline modules — I verified the pattern concretely in `locks.py` and confirmed via the source-scan tests that no other site can bypass it, but did not individually read every module listed in `VOCABULARIES`/`COLUMNS`.
- I did not run the test suite myself to confirm current green status; I'm relying on the static content of `tests/test_vocabulary.py` as read.
