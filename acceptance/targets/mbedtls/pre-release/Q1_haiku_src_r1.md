# Q1 — src — haiku — run 1

Yes, mbedtls **does use mutexes extensively** for thread-safe access to shared resources. Here's where and how:

## Threading Architecture

mbedtls provides a threading abstraction layer with a pluggable implementation (`include/mbedtls/threading.h:27-103`). The default implementation uses POSIX pthread mutexes when `MBEDTLS_THREADING_PTHREAD` is defined.

## Global Mutexes

The library defines several **global mutexes** (`include/mbedtls/threading.h:105-159`):

1. **`mbedtls_threading_readdir_mutex`** (`include/mbedtls/threading.h:120`) — Protects directory reading operations when `MBEDTLS_FS_IO` is enabled.

2. **`mbedtls_threading_gmtime_mutex`** (`include/mbedtls/threading.h:130`) — Protects calls to the non-reentrant `gmtime()` function. Used in `library/platform_util.c:189-201` to serialize access when `MBEDTLS_HAVE_TIME_DATE` is enabled without a thread-safe alternative.

3. **PSA Crypto Mutexes** (`include/mbedtls/threading.h:133-159`):
   - **`mbedtls_threading_key_slot_mutex`** — Protects the key store (`global_data.key_slots`), key slot state transitions, and reader registration. Used throughout `library/psa_crypto.c` and `library/psa_crypto_slot_management.c`.
   - **`mbedtls_threading_psa_globaldata_mutex`** — Protects general PSA global data and initialization state.
   - **`mbedtls_threading_psa_rngdata_mutex`** — Protects PSA RNG state and data.

## Per-Context Mutexes

The SSL session cache includes a per-context mutex (`include/mbedtls/ssl_cache.h:71-72`) embedded in `mbedtls_ssl_cache_context`. This is locked during cache get/set/remove operations (`library/ssl_cache.c:84-86` and `library/ssl_cache.c:259`).

## How the Locking Works

**Function pointer pattern:** The library uses function pointers initialized at runtime (`library/threading.c:101-104`):
```c
void (*mbedtls_mutex_init)(mbedtls_threading_mutex_t *) = threading_mutex_init_pthread;
void (*mbedtls_mutex_free)(mbedtls_threading_mutex_t *) = threading_mutex_free_pthread;
int (*mbedtls_mutex_lock)(mbedtls_threading_mutex_t *) = threading_mutex_lock_pthread;
int (*mbedtls_mutex_unlock)(mbedtls_threading_mutex_t *) = threading_mutex_unlock_pthread;
```

**Pthread implementation** (`library/threading.c:50-99`):
- `threading_mutex_init_pthread()` calls `pthread_mutex_init()` (`library/threading.c:63`)
- `threading_mutex_lock_pthread()` calls `pthread_mutex_lock()` and returns `MBEDTLS_ERR_THREADING_MUTEX_ERROR` on failure (`library/threading.c:75-86`)
- `threading_mutex_unlock_pthread()` calls `pthread_mutex_unlock()` similarly (`library/threading.c:88-99`)

**Example usage** — PSA RNG access (`library/psa_crypto_random.c:147`):
```c
mbedtls_mutex_lock(&mbedtls_threading_psa_rngdata_mutex);
// ... access RNG state ...
mbedtls_mutex_unlock(&mbedtls_threading_psa_rngdata_mutex);
```

## Thread-Safety Scope

As documented in `docs/architecture/psa-thread-safety/psa-thread-safety.md:3-5`, **only the PSA Crypto key management API and `psa_crypto_init` are thread-safe as of Mbed TLS 3.6**. The mutex protection is conditional on `MBEDTLS_THREADING_C` being enabled.

## Alternative Implementations

Users can provide custom threading implementations via `mbedtls_threading_set_alt()` (`include/mbedtls/threading.h:94-97`) to use mutexes with non-pthread platforms.

## Gaps

- I did not trace all 40+ mutex lock/unlock call sites across the codebase, only verified the key ones.
- The exact contention characteristics and performance implications were not analyzed.
- Whether additional functions beyond key management will be made thread-safe in future versions is specification, not implementation.
