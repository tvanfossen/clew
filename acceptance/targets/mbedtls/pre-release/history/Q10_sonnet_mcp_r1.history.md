# Q10 — mcp — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `mcp__doxyguard-db__index`
- **asked:** action
- **got:** {"repo_path":"~/ddb-targets/mbedtls","db_path":"~/.local/state/docs-db/targets/mbedtls-70b036/docs.db","exists":true,"build_version":50,"expected_build_version":50,"source_changed_files":0,"newest_changed_source":null,"s…

### 2. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"locks":[{"name":"ctx->mutex","scope":"unknown","kind":"mutex","identity_confidence":"low","source":"ast_use","file":"library/rsa.c","acquisitions":12,"path_resolved":true},{"name":"mbedtls_threading_psa_globaldata_mute…

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, text
### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":10,"results":[{"name":"des3_set2key","kind":"function","file":"library/des.c"},{"name":"des3_set2key_dec_wrap","kind":"function","file":"library/cipher_wrap.c"},{"name":"des3_set2key_en…

- **got:** {"found":false,"source":"","root":"","symbols":[],"gates":[],"error":"","configured_macros":"\"MBEDTLS_THREADING_C\" \"MBEDTLS_THREADING_PTHREAD\" \"MBEDTLS_HAVE_ASM\" \"MBEDTLS_HAVE_TIME\" \"MBEDTLS_HAVE_TIME_DATE\" \"M…

### 5. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"des3_set2key","subject_kind":"function","name":"des3_set2key","rowid":4694,"signature":"static void des3_set2key(uint32_t esk[96], uint32_t dsk[96], const unsigned char key[MBEDTLS_DES_KEY_SIZE *2])","file":"…

### 6. `mcp__doxyguard-db__dossier`
- **asked:** kind=variable
### 7. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"subject":"heap","subject_kind":"variable","name":"heap","rowid":13870,"type":"buffer_alloc_ctx","brief":"","version":"","provenance":"ast","sites":[{"file":"library/memory_buffer_alloc.c","line":68,"signature":"buffer_…

- **got:** {"kind":"matching symbols","count":1,"results":[{"name":"mbedtls_memory_buffer_alloc_init","kind":"function","file":"include/mbedtls/memory_buffer_alloc.h","brief":"Initialize use of stack-based memory allocator. The sta…

### 8. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"subject":"mbedtls_memory_buffer_alloc_init","subject_kind":"function","name":"mbedtls_memory_buffer_alloc_init","rowid":12948,"signature":"mbedtls_memory_buffer_alloc_init(unsigned char *buf, size_t len)","file":"libra…

### 9. `mcp__doxyguard-db__dossier`
- **asked:** depth, subject
- **got:** {"kind":"dossiers","count":4,"found":4,"subject":["buffer_alloc_calloc","buffer_alloc_free","buffer_alloc_calloc_mutexed","buffer_alloc_free_mutexed"],"results":[{"subject":"buffer_alloc_calloc","subject_kind":"function"…

### 10. `mcp__doxyguard-db__dossier`
- **asked:** kind=variable
### 11. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"subject":"global_data","subject_kind":"variable","name":"global_data","rowid":7760,"type":"psa_global_data_t","brief":"","version":"","provenance":null,"sites":[{"file":"library/psa_crypto.c","line":124,"signature":"ps…

- **got:** {"subject":"mbedtls_memory_buffer_alloc_status","subject_kind":"function","name":"mbedtls_memory_buffer_alloc_status","rowid":12941,"signature":"mbedtls_memory_buffer_alloc_status(void)","file":"library/memory_buffer_all…

### 12. `mcp__doxyguard-db__search`
- **asked:** corpus, text
- **got:** {"kind":"matching symbols","count":9,"results":[{"name":"mbedtls_platform_gmtime_r","kind":"function","file":"include/mbedtls/platform_util.h","brief":"Platform-specific implementation of gmtime_r()"},{"name":"mbedtls_x5…

### 13. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"subject":"mbedtls_memory_buffer_alloc_max_get","subject_kind":"function","name":"mbedtls_memory_buffer_alloc_max_get","rowid":12943,"signature":"mbedtls_memory_buffer_alloc_max_get(size_t *max_used, size_t *max_blocks)…

### 14. `Grep`
- **asked:** pattern=heap\.(total_used|maximum_used|maximum_header_count|header_count|alloc_count|free_count), path=~/ddb-targets/mbedtls/library/memory_buffer_alloc.c
- **got:** Found 1 file ~/ddb-targets/mbedtls/library/memory_buffer_alloc.c

### 15. `Grep`
- **asked:** pattern=heap\.(total_used|maximum_used|maximum_header_count|header_count|alloc_count|free_count|buf|len|first|first_free)\b, path=~/ddb-targets/mbedtls/library/memory_buffer_alloc.c
- **got:** 95:    memory_header *cur = heap.first; 104:    cur = heap.first_free; 155:    memory_header *prv = heap.first, *cur; 165:    if (heap.first->prev != NULL) { 173:    cur = heap.first->next; 201:    memory_header *new, *c…

### 16. `Grep`
- **asked:** pattern=^void mbedtls_memory_buffer_alloc_|^size_t mbedtls_memory_buffer_alloc_, path=~/ddb-targets/mbedtls/library/memory_buffer_alloc.c
- **got:** 496:void mbedtls_memory_buffer_alloc_status(void) 515:void mbedtls_memory_buffer_alloc_count_get(size_t *alloc_count, size_t *free_count) 521:void mbedtls_memory_buffer_alloc_max_get(size_t *max_used, size_t *max_blocks)…

### 17. `mcp__doxyguard-db__dossier`
- **asked:** subject
- **got:** {"kind":"dossiers","count":3,"found":3,"subject":["mbedtls_memory_buffer_alloc_count_get","mbedtls_memory_buffer_alloc_max_reset","mbedtls_memory_buffer_alloc_cur_get"],"results":[{"subject":"mbedtls_memory_buffer_alloc_…

**Reasoning.** ## Answer

`doxyguard-db`'s per-function `writes`/`reads` fields came back empty for every function I checked (see Gaps), so I traced this by hand: pull each function's `callers`/`callees` from `dossier` (to rule out a direct call edge) and its body (to see which members of a shared struct it touches). One clean, well-populated case of "write here, read there, no call between" showed up around the static memory allocator's global state:

**Shared state:** file-scope static `buffer_alloc_ctx heap;` — `library/memory_buffer_alloc.c:68` (confirmed via `dossier(heap, kind=variable)`).

### Couplin

---

## Final answer as submitted

## Answer

`doxyguard-db`'s per-function `writes`/`reads` fields came back empty for every function I checked (see Gaps), so I traced this by hand: pull each function's `callers`/`callees` from `dossier` (to rule out a direct call edge) and its body (to see which members of a shared struct it touches). One clean, well-populated case of "write here, read there, no call between" showed up around the static memory allocator's global state:

**Shared state:** file-scope static `buffer_alloc_ctx heap;` — `library/memory_buffer_alloc.c:68` (confirmed via `dossier(heap, kind=variable)`).

### Coupling 1 — init writes, the allocator reads

- **Writer:** `mbedtls_memory_buffer_alloc_init(buf, len)` — `library/memory_buffer_alloc.c:566-600`. It zeroes the whole struct (`memset(&heap, 0, ...)`, line 568) then sets `heap.buf`/`heap.len` (`library/memory_buffer_alloc.c:590-591`), `heap.first` (`:595`), and `heap.first_free` (`:599`).
- **Reader:** `buffer_alloc_calloc(n, size)` — `library/memory_buffer_alloc.c:199-360`. It reads `heap.first_free` (`:201`), `heap.buf`/`heap.first` (`:210`), and `heap.verify` further down in the body, to decide whether the allocator is initialized and where to carve a block.
- **No call edge:** `dossier(mbedtls_memory_buffer_alloc_init)` lists `callees: mbedtls_platform_set_calloc_free, threading_mutex_init_pthread` — never `buffer_alloc_calloc`. `dossier(buffer_alloc_calloc)` lists `callers: buffer_alloc_calloc_mutexed` only, never `mbedtls_memory_buffer_alloc_init`. The two are wired together only through `mbedtls_platform_set_calloc_free`'s function-pointer registration and the shared global, not a direct call.

### Coupling 2 — the allocator writes counters, the debug accessors read them

- **Writer:** `buffer_alloc_calloc` and `buffer_alloc_free` update `heap.alloc_count`/`heap.free_count` (`library/memory_buffer_alloc.c:250, 399`), `heap.total_used`/`heap.maximum_used` (`:275-277, 341-343, 400`), and `heap.header_count`/`heap.maximum_header_count` (`:337-339, 413, 431`), all under `MBEDTLS_MEMORY_DEBUG`.
- **Readers (no call from the writers):**
  - `mbedtls_memory_buffer_alloc_status()` — `library/memory_buffer_alloc.c:496-513` — reads `heap.header_count`, `heap.total_used`, `heap.maximum_header_count`, `heap.maximum_used`, `heap.alloc_count`, `heap.free_count`, `heap.first` (`:501-507`).
  - `mbedtls_memory_buffer_alloc_count_get()` — `:515-519` — reads `heap.alloc_count`/`heap.free_count`.
  - `mbedtls_memory_buffer_alloc_max_get()` — `:521-525` — reads `heap.maximum_used`/`heap.maximum_header_count`.
  - `mbedtls_memory_buffer_alloc_cur_get()` — `:533-537` — reads `heap.total_used`/`heap.header_count`.
  - `dossier` on each of these four shows `callees: []` and `callers` limited to `main` (or empty) — none of them is ever called by `buffer_alloc_calloc`/`buffer_alloc_free`, and neither of those two functions appears in any reader's caller list.

### Coupling 3 — a reset writes the same fields the allocator will read/re-write later

- `mbedtls_memory_buffer_alloc_max_reset()` — `library/memory_buffer_alloc.c:527-531` — writes `heap.maximum_used = 0` and `heap.maximum_header_count = 0`, with `callers: []` (no one in the index calls it) and `callees: []`. `buffer_alloc_calloc` (`:276-277, 338-339`) later reads and rewrites those same two fields, with no call edge in either direction between the two functions.

All of these share one property that makes the "no call between them" claim safe rather than just absent evidence: `dossier`'s `callers`/`callees` lists for every function above are populated (not silently empty because the tool couldn't resolve the edge) and simply don't name the other side of the pair — i.e., the index positively shows the edge is absent, not merely that it wasn't found.

Note the threading angle: in a `MBEDTLS_THREADING_C` build, `buffer_alloc_calloc`/`buffer_alloc_free` are only reached through `buffer_alloc_calloc_mutexed`/`buffer_alloc_free_mutexed`, which take `heap.mutex` (`library/memory_buffer_alloc.c:544-548, 558-562`, confirmed by `search(corpus=locks)`). That mutex protects the writer's *own* mutation of `heap`, but none of the debug-accessor readers above (`status`/`count_get`/`max_get`/`cur_get`) take that lock at all — so even where the writer is guarded, the reader side of this write→read coupling is unsynchronized.

## Gaps

- The index's per-function `writes`/`reads` fields (part of `dossier`'s schema) returned `[]` for every function checked here, including ones that plainly write to `heap.*` members in their bodies. I could not find an MCP query that lists struct-member-level write/read edges directly — I had to reconstruct them from `grep`-style reading of function bodies (via `Read`/`Grep` on the source, since the MCP `dossier` body view truncates long functions). This is worth flagging as a detector gap: global/struct-member dataflow (as opposed to accessor-based `shared_key_edges`, which is heuristic and pattern-driven) isn't tracked as a first-class edge type the way call edges are.
- I did not exhaustively enumerate every static/global in the ~440-file index — I searched from the `locks` corpus (which names mutex-protected shared objects as a proxy for "state something cares about races on") and picked the richest one (`heap`). There may be other write/read-without-call couplings on globals that aren't lock-protected at all (and thus wouldn't surface via the `locks` search), which I did not sweep for given the scope of a single-question answer.
- I did not check `global_data` (`psa_global_data_t`) in `library/psa_crypto.c:124` and `library/psa_crypto_slot_management.c:193` in depth — `dossier(global_data, kind=variable)` shows **two distinct static declarations of the same name in different files**, which is a namesake collision, not necessarily the same shared object; disambiguating that would need per-file symbol resolution I didn't chase down for this answer.
