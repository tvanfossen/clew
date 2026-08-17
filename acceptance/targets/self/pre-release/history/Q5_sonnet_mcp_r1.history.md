# Q5 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":25,"results":[{"name":"doxyguard_db::vocabulary::DeclarationError","kind":"class","file":"doxyguard_db/vocabulary.py","brief":"A declared config value outside its schema vocabulary."},{…

### 2. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"kind":"dossiers","count":3,"found":2,"subject":["doxyguard_db/vocabulary.py","doxyguard_db::vocabulary::Vocabulary","doxyguard_db::vocabulary::DeclarationError"],"results":[{"name":"doxyguard_db/vocabulary.py","found":…

### 3. `mcp__doxyguard-db__dossier`
- **asked:** kind=file
- **got ⚠ error:** Error executing tool dossier: Subject kind 'file' names no dossier subject: a file has no dossier — its documentation is `search(corpus='prose')`.

### 4. `mcp__doxyguard-db__dossier`
- **asked:** depth, qualified, subject, target
- **got:** {"kind":"dossier","subject":"check","found":false,"note":"No dossier for 'check' in this index. This is a definitive negative from the database, NOT an error and NOT a malformed call. Before concluding the symbol does no…

### 5. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/vocabulary.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""The schema's enumerated vocabularies — ONE definition per value set. 3	 4	Every enumerated column in docs.db used to spell its allowed values as a SQL 5	string literal at the CREATE …

### 6. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject, target
- **got:** {"subject":"check","subject_kind":"function","name":"check","rowid":894,"signature":" str doxyguard_db.vocabulary.Vocabulary.check(self, str column)","file":"doxyguard_db/vocabulary.py","line_start":129,"line_end":139,"b…

### 7. `mcp__doxyguard-db__dossier`
- **asked:** depth, qualified, subject, target
- **got:** {"subject":"check","subject_kind":"function","name":"check","rowid":5903,"signature":"check(table: str, column: str)","file":"doxyguard_db/vocabulary.py","line_start":1030,"line_end":1040,"brief":"SQL CHECK clause constr…

### 8. `Grep`
- **asked:** pattern=vocabulary\.(check|bool_check|validated), path=~/ddb-targets/self/doxyguard_db
- **got:** No files found

### 9. `Grep`
- **asked:** pattern=from doxyguard_db.vocabulary import|from \.vocabulary import|import vocabulary|vocabulary\.\w+\(|vocab\.check\(|_vocab\.check\(, path=~/ddb-targets/self/doxyguard_db
- **got:** Found 24 files ~/ddb-targets/self/doxyguard_db/vocabulary.py ~/ddb-targets/self/doxyguard_db/threads.py ~/ddb-targets/self/doxyguard_db/shared_key_edges.py ~/ddb-targets/self/doxyguard_db/reachability.py ~/ddb-targets/se…

### 10. `Grep`
- **asked:** pattern=vocabulary\.check\(|from \. import vocabulary|import doxyguard_db\.vocabulary, path=~/ddb-targets/self/doxyguard_db
- **got:** No matches found

### 11. `Grep`
- **asked:** pattern=vocabulary, path=~/ddb-targets/self/doxyguard_db/schema.py
- **got ⚠ error:** <tool_use_error>Path does not exist: ~/ddb-targets/self/doxyguard_db/schema.py. Note: your current working directory is ~/Projects/docs-db/.claude/tmp/bench/p9-self/wd.</tool_use_error>

### 12. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"indexed files","count":0,"results":[],"subject":"schema","note":"No indexed file matches 'schema'. This corpus holds INDEXED SOURCE FILES only, so a build script, a Doxyfile, a data file or anything else the ind…

### 13. `mcp__doxyguard-db__search`
- **asked:** corpus, target, text
- **got:** {"kind":"matching symbols","count":25,"results":[{"name":"_create_req_edges_table","kind":"function","file":"doxyguard_db/requirements.py","brief":"Create (or reset) the req_edges table + indexes."},{"name":"_create_req_…

### 14. `Grep`
- **asked:** pattern=vocabulary\.|from \.vocabulary|import vocabulary, path=~/ddb-targets/self/doxyguard_db/locks.py
- **got:** 74:from .vocabulary import ( 300:    Every enumerated CHECK is generated from `vocabulary.COLUMNS`. The three 761:## @brief The lock stage's harvester for one declared lock vocabulary. 995:## The pairing that identifies …

### 15. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/locks.py
- **got:** 280	        return source 281	    import yaml 282	 283	    return yaml.safe_load(Path(source).read_text(encoding="utf-8")) or {} 284	 285	 286	## @brief Create the L1 lock tables if they do not exist. 287	## @param conn …

**Reasoning.** Confirmed — the DDL for each layer calls `check("locks", "kind")` (module-level `vocabulary.check`) inline to splice the CHECK clause into `CREATE TABLE`. Now let's confirm the `LOCK_KIND` identity collapse consequence and the merge scenario, plus tests that guard against a raw literal restating a value set.

### 16. `Grep`
- **asked:** pattern=no_raw_check_literal|def test_no_raw_check|def test_every_registered_column, path=~/ddb-targets/self/tests/test_vocabulary.py
- **got:** 96:def test_no_raw_check_literal_survives_outside_vocabulary() -> None: 97-    """The whole point of the module: `CHECK(` may appear in exactly ONE file. 98- 99-    An artifact reconcile cannot catch a hand-rolled CHECK …

**Reasoning.** This confirms the enforcement mechanism precisely. I have everything needed.

## Answer

**The single source is `doxyguard_db/vocabulary.py`** (`doxyguard_db/vocabulary.py:1-1081`). Its module docstring states the mandate directly: "Every enumerated column in docs.db used to spell its allowed values as a SQL string literal at the CREATE TABLE site, and sometimes a SECOND time as a module constant... This module is the single source." (`doxyguard_db/vocabulary.py:2-14`).

**Mechanism.** Each enumerated value set is one frozen `Vocabulary` dataclass instance (`doxyguard_db/vocabulary.py:100-171`

---

## Final answer as submitted

This confirms the enforcement mechanism precisely. I have everything needed.

## Answer

**The single source is `doxyguard_db/vocabulary.py`** (`doxyguard_db/vocabulary.py:1-1081`). Its module docstring states the mandate directly: "Every enumerated column in docs.db used to spell its allowed values as a SQL string literal at the CREATE TABLE site, and sometimes a SECOND time as a module constant... This module is the single source." (`doxyguard_db/vocabulary.py:2-14`).

**Mechanism.** Each enumerated value set is one frozen `Vocabulary` dataclass instance (`doxyguard_db/vocabulary.py:100-171`): `id`, an ordered `values: tuple[str, ...]`, `means` (semantics), an explicit `rank` map, and a `reserved` frozenset. Two methods are the only way anything is allowed to touch a vocabulary's values:
- `Vocabulary.check(column)` (`doxyguard_db/vocabulary.py:129-138`) generates a `CHECK(col IN (...))` SQL fragment by explicit quote-and-join (never `{tuple!r}` — noted at `doxyguard_db/vocabulary.py:29-36,130-132` because a repr-based join breaks on 1-value sets and apostrophes).
- `Vocabulary.validated(value, owner=, field=)` (`doxyguard_db/vocabulary.py:159-171`) is the "single choke point every declared-enum path routes through," raising `DeclarationError` (`doxyguard_db/vocabulary.py:65-76`) rather than normalizing an unknown token.

All 33 vocabularies are registered in `VOCABULARIES` (`doxyguard_db/vocabulary.py:895-933`), and every DDL column that should carry a CHECK is bound to its vocabulary in `COLUMNS: dict[tuple[str,str], Vocabulary]` (`doxyguard_db/vocabulary.py:938-973`). A module-level `check(table, column)` (`doxyguard_db/vocabulary.py:1030-1040`) looks up `COLUMNS` and raises `KeyError` for anything unregistered — "a silently-absent CHECK is the exact hole this module exists to close."

**How the rest of the codebase is kept from restating them.** Each layer's own table-creation function imports `check`/`bool_check` from `vocabulary` and splices the clause inline, e.g. `doxyguard_db/locks.py:320`: `kind TEXT NOT NULL {check("locks", "kind")}`. Nothing else is allowed to write `CHECK(` literally: `tests/test_vocabulary.py:96-111` scans every package source file and asserts `"CHECK("` appears in exactly one file, `vocabulary.py` itself — a filesystem-level gate, since `pre-commit --all-files` can't see a brand-new untracked file and an artifact-reconcile test can't see a CREATE TABLE the fixture build never runs. `tests/test_vocabulary.py:412-418` separately asserts every registered `(table, column)` produces a valid clause and that an unregistered one raises.

**Dependencies, and why.** The module docstring is explicit that it is a **true leaf** (`doxyguard_db/vocabulary.py:16-20`): zero intra-package imports — not even `doxyguard_db/_common.py` (which pulls in `rich`) or `doxyguard_db/query/_common.py` (deliberately stdlib-only). It imports only `dataclasses` and `pathlib`. The reason: importing either of those two dependency-bearing modules here would make one of them un-importable without dragging in the other's dependency (`rich` vs. stdlib-only), since every other layer (locks, threads, shared_key_edges, kconfig, datamodel, etc. — 24 files import from it, confirmed by grep) depends on `vocabulary.py`, so it must depend on nothing back.

**What breaks if two entries that "look identical" get merged.** The docstring calls this out directly (`doxyguard_db/vocabulary.py:22-27`): five vocabularies (spawn-detection strength, provenance strength, lock-identity certainty, acquisition-resolution success, and `external_boundaries` confidence) all happen to share the tuple `('low','medium','high')` and are deliberately kept as five separate objects. If two were merged into one shared `Vocabulary`, adding a value for one purpose (e.g. widening lock-identity confidence) would silently widen the `CHECK` constraint on the other four unrelated columns too — and every test comparing the shipped schema against the registry would stay green, because the schema-reconcile test only checks that the CHECK text matches what the registry emits, not that the registry's *grouping* is semantically correct.

The sharper case is `LOCK_KIND` (`doxyguard_db/vocabulary.py:377-385`), where the module docstring states `locks.kind` is **part of lock identity** — `UNIQUE(name, scope, kind)`. If two kind values that "look identical" (e.g. two spellings that get merged/normalized to one token) were collapsed, two acquisitions naming genuinely different lock kinds would collapse into **one lock row**, fabricating shared synchronization between two things that don't actually share a lock — exactly the failure the fail-closed `validated()` (no `'unknown'` fallback for `acq_form`/`acq_role`/`acq_mode`, per `doxyguard_db/vocabulary.py:38-45`) exists to prevent.

## Gaps

- I could not get `dossier`'s `callers` to show who invokes `check("locks","kind")` etc. — it returned empty for both the `Vocabulary.check` method and the module-level `check` function (likely the same name-collision limitation this repo's own memory notes document for overloaded/same-named symbols, e.g. `gh#26`). I resolved actual call sites by `Grep` on `doxyguard_db/locks.py` instead and verified inline usage directly in the source.
- `dossier(kind="file")` on `doxyguard_db/vocabulary.py` was refused ("a file has no dossier"); file-level brief came from `search(corpus="symbols")`'s file-doc provenance instead.
