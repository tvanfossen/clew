# Q1 — mcp — haiku — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

**Reasoning.** I'll investigate whether mbedtls uses mutexes or locking by querying the indexed repository.

### 1. `mcp__doxyguard-db__search`
- **asked:** corpus, target
- **got:** {"locks":[{"name":"ctx->mutex","scope":"unknown","kind":"mutex","identity_confidence":"low","source":"ast_use","file":"library/rsa.c","acquisitions":12,"path_resolved":true},{"name":"mbedtls_threading_psa_globaldata_mute…

### 2. `mcp__doxyguard-db__dossier`
- **asked:** kind=variable
- **got:** {"kind":"dossiers","count":4,"found":4,"subject":["mbedtls_threading_psa_globaldata_mutex","mbedtls_threading_key_slot_mutex","mbedtls_threading_psa_rngdata_mutex","mbedtls_threading_gmtime_mutex"],"results":[{"subject":…

### 3. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"lock unlock mutex acquire","note":"No matching symbols for 'lock unlock mutex acquire'. This is NOT an error and NOT a malformed call, and it is NOT a definiti…

### 4. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":4,"results":[{"name":"threading_mutex_lock_pthread","kind":"function","file":"library/threading.c"},{"name":"threading_mutex_unlock_pthread","kind":"function","file":"library/threading.…

### 5. `mcp__doxyguard-db__dossier`
- **asked:** subject, target
- **got:** {"kind":"dossiers","count":4,"found":4,"subject":["threading_mutex_lock_pthread","threading_mutex_unlock_pthread","mbedtls_mutex_lock","mbedtls_mutex_unlock"],"results":[{"subject":"threading_mutex_lock_pthread","subject…

### 6. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"subject":"mbedtls_rsa_private","subject_kind":"function","name":"mbedtls_rsa_private","rowid":3686,"signature":"int mbedtls_rsa_private(mbedtls_rsa_context *ctx, int(*f_rng)(void *, unsigned char *, size_t), void *p_rn…

### 7. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"subject":"psa_get_and_lock_key_slot","subject_kind":"function","name":"psa_get_and_lock_key_slot","rowid":7164,"signature":"psa_status_t psa_get_and_lock_key_slot(mbedtls_svc_key_id_t key, psa_key_slot_t **p_slot)","fi…

### 8. `mcp__doxyguard-db__search`
- **asked:** corpus, limit, target, text
- **got:** {"kind":"matching symbols","count":0,"results":[],"subject":"ssl cache mutex","note":"No matching symbols for 'ssl cache mutex'. This is NOT an error and NOT a malformed call, and it is NOT a definitive negative either. …

### 9. `mcp__doxyguard-db__dossier`
- **asked:** max_body_lines, subject, target
- **got:** {"kind":"dossiers","count":2,"found":2,"subject":["mbedtls_ssl_cache_get","mbedtls_ssl_cache_set"],"results":[{"subject":"mbedtls_ssl_cache_get","subject_kind":"function","name":"mbedtls_ssl_cache_get","rowid":9823,"sign…

**Reasoning.** ## Answer

**Yes, mbedtls extensively uses mutexes and locking for thread safety.** The library implements a configurable threading abstraction layer and uses mutexes to protect shared resources across multiple concurrent threads.

### Locking Infrastructure

The threading system is defined in `library/threading.c:189-190` and exposed via `include/mbedtls/threading.h`. The library uses pthread mutexes on POSIX systems through:

- `library/threading.c:103` — `mbedtls_mutex_lock` (function pointer initialized to `threading_mutex_lock_pthread`)
- `library/threading.c:104` — `mbedtls_mutex_unlock`

---

## Final answer as submitted

## Answer

**Yes, mbedtls extensively uses mutexes and locking for thread safety.** The library implements a configurable threading abstraction layer and uses mutexes to protect shared resources across multiple concurrent threads.

### Locking Infrastructure

The threading system is defined in `library/threading.c:189-190` and exposed via `include/mbedtls/threading.h`. The library uses pthread mutexes on POSIX systems through:

- `library/threading.c:103` — `mbedtls_mutex_lock` (function pointer initialized to `threading_mutex_lock_pthread`)
- `library/threading.c:104` — `mbedtls_mutex_unlock` (function pointer initialized to `threading_mutex_unlock_pthread`)

These function pointers are set to the concrete implementations:
- `library/threading.c:75-86` — `threading_mutex_lock_pthread()` wraps `pthread_mutex_lock()`
- `library/threading.c:88-99` — `threading_mutex_unlock_pthread()` wraps `pthread_mutex_unlock()`

### Global Mutexes

The library defines 10 distinct mutex identities, all declared in `library/threading.c` (lines 185-190):

1. **`mbedtls_threading_gmtime_mutex`** — Protects `gmtime_r()` calls in `library/platform_util.c:1` (platform-level time operations)
2. **`mbedtls_threading_key_slot_mutex`** — Protects PSA key slot access in `library/psa_crypto.c` (8 acquisitions)
3. **`mbedtls_threading_psa_globaldata_mutex`** — Protects PSA global state in `library/psa_crypto.c` (9 acquisitions)
4. **`mbedtls_threading_psa_rngdata_mutex`** — Protects PSA random number generator state in `library/psa_crypto.c` (8 acquisitions)
5. **`mbedtls_threading_readdir_mutex`** — Protects `readdir()` calls in `library/x509_crt.c:1`
6. **Context-specific mutexes**:
   - `ctx->mutex` in `library/rsa.c` (12 acquisitions) — Per-RSA context mutex
   - `cache->mutex` in `library/ssl_cache.c` (3 acquisitions) — Per-cache instance mutex
   - `heap.mutex` in `library/memory_buffer_alloc.c` (2 acquisitions) — Memory allocator protection

### How Locking Works: Representative Examples

**RSA Private Key Operations** — `library/rsa.c:1476-1661`

The RSA private operation acquires the context's mutex at line 1518 before performing cryptographic computations, protecting against concurrent modifications to the RSA context. The lock is held through the entire modular exponentiation sequence (lines 1518-1631) and released before returning.

```c
// library/rsa.c:1518
if ((ret = mbedtls_mutex_lock(&ctx->mutex)) != 0) {
    return ret;
}
// ... RSA computations protected by mutex ...
// Released at line 1631
mbedtls_mutex_unlock(&ctx->mutex);
```

**PSA Key Slot Management** — `library/psa_crypto_slot_management.c:822-891`

PSA crypto locks the key slot mutex before accessing or loading key slots to prevent race conditions when multiple threads access the same key. The lock ensures atomicity when checking if a key is already loaded versus loading it freshly.

```c
// library/psa_crypto_slot_management.c:822
PSA_THREADING_CHK_RET(mbedtls_mutex_lock(&mbedtls_threading_key_slot_mutex));
// ... key slot operations ...
PSA_THREADING_CHK_RET(mbedtls_mutex_unlock(&mbedtls_threading_key_slot_mutex));
```

**SSL Session Cache** — `library/ssl_cache.c:84-105` (get) and `library/ssl_cache.c:259-308` (set)

Both cache operations acquire `cache->mutex` to protect concurrent reads and writes to the session cache.

```c
// library/ssl_cache.c:84 (cache get)
if ((ret = mbedtls_mutex_lock(&cache->mutex)) != 0) {
    return ret;
}
// Find and deserialize cached session
mbedtls_mutex_unlock(&cache->mutex);
```

### Summary

**Locking protects:**
- RSA cryptographic operations (per-context locking)
- PSA key slots and random number state (global mutexes)
- SSL session cache (per-cache locking)
- Heap allocator state
- Platform functions (`gmtime_r`, `readdir`)
- Entropy gathering operations

All locking is **conditional on `MBEDTLS_THREADING_C`** compile flag and uses function-pointer indirection to allow custom threading implementations beyond pthread.

## Gaps

None identified. The index answered all structural questions about where and how locking is used.
