# Q1 — mcp — haiku — run 1

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
