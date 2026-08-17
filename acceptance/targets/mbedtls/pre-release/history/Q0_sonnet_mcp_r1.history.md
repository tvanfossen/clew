# Q0 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__index`
- **asked:** action, target
- **got ⚠ error:** Error executing tool index: index(action='status') does not take a target, and '~/ddb-targets/mbedtls' was supplied. Refusing rather than ignoring it, because this action reports on the DERIVED target and on where that d…

### 2. `mcp__doxyguard-db__index`
- **asked:** action
- **got:** {"repo_path":"~/ddb-targets/mbedtls","db_path":"~/.local/state/docs-db/targets/mbedtls-70b036/docs.db","exists":true,"build_version":50,"expected_build_version":50,"source_changed_files":0,"newest_changed_source":null,"s…

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, target
- **got:** {"directories":[{"directory":"library","indexed_files":174,"symbols":4690,"external_files":0,"unresolved_files":0},{"directory":"include","indexed_files":97,"symbols":4057,"external_files":0,"unresolved_files":0},{"direc…

### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"indexed files","count":197,"results":[{"path":"3rdparty/everest/library/Hacl_Curve25519.c","symbol_count":47},{"path":"3rdparty/everest/library/Hacl_Curve25519_joined.c","symbol_count":4},{"path":"3rdparty/evere…

### 5. `mcp__doxyguard-db__search`
- **asked:** corpus, target
- **got:** {"locks":[{"name":"ctx->mutex","scope":"unknown","kind":"mutex","identity_confidence":"low","source":"ast_use","file":"library/rsa.c","acquisitions":12,"path_resolved":true},{"name":"mbedtls_threading_psa_globaldata_mute…

**Reasoning.** ## Coverage check for `~/ddb-targets/mbedtls`

**What I checked and what came back:**

1. `index(action="status")` (no target — reports the derived default, which resolves to this repo via `--repo`): `build_version 50`, `expected_build_version 50`, `source_changed_files 0`, `stale: false`, `age_days 0`. The index is current — no rebuild needed, and none was performed.
2. `search(corpus="files")` against the target: **527 indexed file rows** across 10 top-level directories (`library` 174/4690 symbols, `include` 97/4057, `programs` 80/965, `tests` 44/859, `3rdparty` 32/454, `docs` 30, `configs` 

---

## Final answer as submitted

## Coverage check for `~/ddb-targets/mbedtls`

**What I checked and what came back:**

1. `index(action="status")` (no target — reports the derived default, which resolves to this repo via `--repo`): `build_version 50`, `expected_build_version 50`, `source_changed_files 0`, `stale: false`, `age_days 0`. The index is current — no rebuild needed, and none was performed.
2. `search(corpus="files")` against the target: **527 indexed file rows** across 10 top-level directories (`library` 174/4690 symbols, `include` 97/4057, `programs` 80/965, `tests` 44/859, `3rdparty` 32/454, `docs` 30, `configs` 13, `scripts` 9, `ChangeLog.d` 1, and a root bucket `.` with 47 files).
3. `coverage` block from `status`: `indexed_files 443`, `substantive_files 330`, `barren_files 2` (`barren_ratio 0.6%`), `undocumented_files 37` (`undocumented_ratio 11.2%`), `unresolved_files 42`.
4. `search(corpus="locks")`: 10 first-party lock identities, 0 external, 0 unresolved — confirms the causal/locking layer is populated (this repo declares an explicit `mbedtls_mutex_lock`/`unlock` pattern per the `options.locks.explicit` block in `status`).

**What I found missing or under-covered:**

- **42 `unresolved_files`, effectively all (41 of 47) in the root `.` bucket** — i.e. top-level non-source files (build scripts, `CMakeLists.txt`, `.md`/`.yml`/config-adjacent files at repo root) that no grammar in the pipeline parses into symbols. This is expected: they aren't C/C++/Python source, so "unresolved" here means "not a reasoning target," not a gap in reasoning about code.
- **37 `undocumented_files` (11.2%)** — files doxygen indexed but with sparse/no doc comments, notably `3rdparty/p256-m/p256-m/p256-m.c`, `tests/src/psa_test_wrappers.c`, `include/mbedtls/config_adjust_legacy_from_psa.h`, `library/aesni.c`. These are indexed and queryable (symbols/calls resolve) but may have thinner `dossier` briefs.
- **`index_scope` is undeclared** for this repo (no `.doxygen-guard.yaml`/`.doxyguard-db.yaml` found) — per the `status` `reason` field, this means the doc build's own `Doxyfile` (`doxygen/mbedtls.doxyfile`, `INPUT: ../include, input, ../tests/include/alt-dummy`, `FILE_PATTERNS: *.h`) is **not** what bounds the index — the whole repo is indexed regardless, which is why `library/*.c` and `programs/*.c` show up despite the Doxyfile only declaring headers as input.
- **1 undeclared spawn primitive**: `thread_create` (diagnostic `undeclared_spawn_primitives`) — a thread-spawn convention the built-in heuristic tier doesn't recognize; worth declaring if thread-boundary questions come up.

**What I did about it:** Nothing needed changing — the index reports `stale: false` at build version 50 matching the running server's expected version, and `source_changed_files: 0`. No refresh was required; I did not run `build_or_refresh`.

**Cost:** 4 MCP calls (`status`, `search files`, `search files *.c`, `search locks`) — no source reads, no shell commands. This is the full coverage check; I'm treating the 41 root-level "unresolved" files and the undeclared `thread_create` spawn primitive as known, acceptable gaps rather than something to fix before answering substantive questions.

## Gaps

- The 41 unresolved root-level files are non-source (build/config/docs at repo root) — not read directly, since the index correctly excludes them from symbol resolution rather than failing on them.
- `thread_create` is flagged as an undeclared spawn primitive — if a later question is specifically about thread spawning via that name, the causal thread layer may miss it since only the heuristic tier is active (no `.doxyguard-db.yaml` override declared).
- No `.doxygen-guard.yaml`/`.doxyguard-db.yaml` exists in this repo, so index scope is "whole repo" by default rather than an explicit declaration — this widens rather than narrows coverage, so it's not a concern for completeness, just worth knowing the boundary is a default, not a stated policy.
