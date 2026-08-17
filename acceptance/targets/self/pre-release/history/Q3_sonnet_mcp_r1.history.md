# Q3 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":5,"results":[{"name":"rejected_doxyfile_candidates","kind":"function","file":"doxyguard_db/doxygen.py","brief":"Doxyfile candidates discovery found but declined to adopt."},{"name":"tes…

### 2. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject, target
- **got:** {"subject":"rejected_doxyfile_candidates","subject_kind":"function","name":"rejected_doxyfile_candidates","rowid":1892,"signature":" list[Path] doxyguard_db.doxygen.rejected_doxyfile_candidates(Path repo)","file":"doxygu…

### 3. `mcp__doxyguard-db__search`
- **asked:** target, text
- **got:** {"kind":"matching symbols","count":6,"results":[{"name":"discover_doxyfile","kind":"function","file":"doxyguard_db/doxygen.py","brief":"Discover a repo's own Doxyfile (declaration-driven, never hardcoded)."},{"name":"tes…

### 4. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject, target
- **got:** {"kind":"dossiers","count":3,"found":3,"subject":["discover_doxyfile","_resolve_doxyfile_and_root","SECTION_DOXYFILE"],"results":[{"subject":"discover_doxyfile","subject_kind":"function","name":"discover_doxyfile","rowid…

### 5. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject, target
- **got:** {"kind":"dossiers","count":4,"found":4,"subject":["describe_doxyfile_resolution","_doxyfile_situation","_DOXYFILE_DIRS","synthesize_doxyfile"],"results":[{"subject":"describe_doxyfile_resolution","subject_kind":"function…

### 6. `Grep`
- **asked:** pattern=^DOXYFILE_|_DOXYFILE_MESSAGES|_DOXYFILE_FATAL_SITUATIONS, path=~/ddb-targets/self/doxyguard_db/doxygen.py
- **got:** Found 1 file ~/ddb-targets/self/doxyguard_db/doxygen.py

### 7. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/doxygen.py
- **got:** 329	## @brief Phrase the explicit-but-absent --doxyfile situation. 330	## @return The message naming the path tried and the flag that changes the outcome. 331	## @version 1 332	## @dg_internal 333	def _msg_explicit_missi…

**Reasoning.** I now have everything needed to answer precisely.

## Answer

**The tool being driven is `doxygen`**, and its configuration file is a **`Doxyfile`**.

### Where it looks

`discover_doxyfile(repo)` (`doxyguard_db/doxygen.py:189-244`) searches exactly two kinds of location, in order, and stops at the first hit:

1. `<repo>/Doxyfile` — the repo root.
2. `<repo>/<d>/Doxyfile` for `d` in `_DOXYFILE_DIRS = ("docs", "doc")` (`doxyguard_db/doxygen.py:181`) — doxygen's own conventional docs directories.

The loop body: `for candidate in (repo / "Doxyfile", *(repo / d / "Doxyfile" for d in _DOXYFILE_DIR

---

## Final answer as submitted

I now have everything needed to answer precisely.

## Answer

**The tool being driven is `doxygen`**, and its configuration file is a **`Doxyfile`**.

### Where it looks

`discover_doxyfile(repo)` (`doxyguard_db/doxygen.py:189-244`) searches exactly two kinds of location, in order, and stops at the first hit:

1. `<repo>/Doxyfile` — the repo root.
2. `<repo>/<d>/Doxyfile` for `d` in `_DOXYFILE_DIRS = ("docs", "doc")` (`doxyguard_db/doxygen.py:181`) — doxygen's own conventional docs directories.

The loop body: `for candidate in (repo / "Doxyfile", *(repo / d / "Doxyfile" for d in _DOXYFILE_DIRS)): if candidate.is_file(): return candidate` (`doxyguard_db/doxygen.py:233-236`). It returns the *first* match and never looks anywhere else — no recursive glob, no other subdirectory.

It deliberately **refuses to guess beyond those trusted locations**. It used to fall back to `sorted(repo.glob("*/Doxyfile"))[0]` — any subdirectory, picked alphabetically — and that once selected a test fixture's `sample/Doxyfile` to index the whole project (`doxyguard_db/doxygen.py:200-210`).

### What it does with files it finds but does not use ("strays")

`rejected_doxyfile_candidates(repo)` (`doxyguard_db/doxygen.py:280-299`) separately globs `repo.glob("*/Doxyfile")` and returns every match that is **not** one of the two trusted paths above (root or `docs/`/`doc/`). These stray Doxyfiles are:

- **Not read, not merged, not adopted** — `discover_doxyfile` still returns `None` for every one of them.
- **Named in the resulting message**, via `describe_doxyfile_resolution` → `_msg_rejected` (`doxyguard_db/doxygen.py:362-374`), which lists the found stray path(s) relative to the repo root and explains why: "found `<path>` under `<root>`, but NOT in a location a project Doxyfile is trusted from … so it was not adopted and a Doxyfile is being synthesized instead."
- The build then proceeds by **synthesizing** its own minimal Doxyfile instead (see below) — the presence of strays does not block anything, it only changes the message.

### The four distinct outcomes (`_doxyfile_situation`, `doxyguard_db/doxygen.py:311-328`, phrased by `describe_doxyfile_resolution`/`_DOXYFILE_MESSAGES`, `doxyguard_db/doxygen.py:329-402`)

| Outcome | Condition | Build continues? |
|---|---|---|
| **`explicit_missing`** | An explicit `--doxyfile <path>` was passed and that path is not on disk. Discovery is never attempted (explicit path overrides it). | **No — fatal.** `_resolve_doxyfile_and_root` calls `sys.exit(1)` (`doxyguard_db/cli.py:2298-2299`). Message tells the user to check the path or pass `--repo-root` instead. |
| **`no_target`** | Neither `--doxyfile` nor `--repo-root` was given. No directory is ever searched. | **No — fatal.** Same `sys.exit(1)` path (`doxyguard_db/cli.py:2298-2299`). |
| **`rejected`** | A `--repo-root` was searched, no trusted Doxyfile was found, but one or more strays exist elsewhere in the repo. | **Yes.** Not fatal; a Doxyfile is synthesized (`synthesize_doxyfile`, `doxyguard_db/doxygen.py:454-508`, called at `doxyguard_db/cli.py:2287`) and indexing proceeds from the repo's declared/whole-repo scope. |
| **`absent`** | A `--repo-root` was searched and genuinely ships no Doxyfile anywhere. | **Yes.** Not fatal — explicitly documented as a "SUPPORTED configuration", not an error. A Doxyfile is synthesized the same way. |

Only the first two (`explicit_missing`, `no_target`) are fatal — `_DOXYFILE_FATAL_SITUATIONS = frozenset({DOXYFILE_EXPLICIT_MISSING, DOXYFILE_NO_TARGET})` (`doxyguard_db/doxygen.py:402`). The other two proceed via a synthesized `Doxyfile` written by `synthesize_doxyfile`, which sets `PROJECT_NAME`, an absolute `OUTPUT_DIRECTORY`, `STRIP_FROM_PATH`, and an empty `INPUT` (`doxyguard_db/doxygen.py:497-503`), with the actual `INPUT` filled in later from the repo's derived scope.

The caller wiring this all together is `_resolve_doxyfile_and_root` (`doxyguard_db/cli.py:2218-2307`), which discovers, checks candidates, and dispatches to synthesis or `sys.exit(1)` per the table above.

## Gaps

- I did not independently verify `DOXYFILE_EXPLICIT_MISSING`/`DOXYFILE_NO_TARGET`/`DOXYFILE_REJECTED`/`DOXYFILE_ABSENT` constants' literal string values (only their usage/behavior) — not load-bearing for the question asked, so not chased further.
- The `mcp_server` build path is noted in `discover_doxyfile`'s docstring as also calling this discovery, but I did not trace that second call site (`_check_indexable`, `_doxyfile_scope`, `_run_build` — all listed as callers by the index) since the CLI path (`_resolve_doxyfile_and_root`) already covers all four outcomes identically.
