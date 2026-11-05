**Short answer:** in the default configuration, the library starts no threads and takes no locks. Any concurrency comes from the application calling into mbedtls from several threads at once, and nothing protects the shared state. Mutexes only exist if you enable `MBEDTLS_THREADING_C` plus an implementation.

**Default configuration**

- `include/mbedtls/mbedtls_config.h:3787` has `//#define MBEDTLS_THREADING_C` commented out. `MBEDTLS_THREADING_PTHREAD` (line 2196) and `MBEDTLS_THREADING_ALT` (line 2185) are also off.
- Every lock site is guarded by `#if defined(MBEDTLS_THREADING_C)`. With the flag off, `mbedtls_mutex_lock` calls and the `PSA_THREADING_CHK_*` macros are compiled out (`library/psa_crypto_core.h`, `library/memory_buffer_alloc.c:540` and similar).
- `library/threading.c` only builds under `MBEDTLS_THREADING_C`, so no mutex code is linked.
- The Makefile (`scripts/common.make:87-96`) links `-lpthread` only when `THREADING_C` and `THREADING_PTHREAD` are both enabled.
- `grep` finds no `pthread_create` or `std::thread` anywhere in `library/` or `include/`.
- The library does not spawn anything. Concurrency means your application calls into it from more than one thread.
- `MBEDTLS_PSA_CRYPTO_C` is on by default (line 3334), so the PSA subsystem's global state exists and is shared across all callers, with no locking.

**What is protected when `MBEDTLS_THREADING_C` is enabled**

| Lock | Protects |
|---|---|
| Per-context `ctx->mutex` | CTR_DRBG, HMAC_DRBG, entropy (`entropy.c`), RSA blinding (`rsa.c`), SSL session cache, SSL ticket context, SSL cookie context |
| `heap.mutex` | `memory_buffer_alloc` heap: calloc/free wrappers only (`memory_buffer_alloc.c:540-565`) |
| `mbedtls_threading_key_slot_mutex` | PSA key slot table (`psa_crypto.c`, `psa_crypto_slot_management.c`) |
| `mbedtls_threading_psa_globaldata_mutex` | PSA global init/state flags, key-slot init state |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state and reseeding after fork (`psa_crypto_random.c:147`) |
| `mbedtls_threading_readdir_mutex` | `readdir` in X.509 directory loading (`x509_crt.c:1611`) |
| `mbedtls_threading_gmtime_mutex` | `gmtime()` fallback, only when `gmtime_r` is unavailable |

Two points about this list:

- The per-context mutexes protect a single object, not the library. Two threads can use separate `mbedtls_ctr_drbg_context`s freely, but sharing one needs the lock.
- With `MBEDTLS_THREADING_ALT` and no `mbedtls_threading_set_alt()` call, the function pointers default to `threading_mutex_fail` (`threading.c:127`), which returns an error. Locking fails closed rather than silently succeeding.

**Caveats**

- The threading header says that if PSA is in use (`MBEDTLS_USE_PSA_CRYPTO` or any PSA call), you need `MBEDTLS_THREADING_C` as soon as more than one thread can reach it. That is the main hazard of the default build: PSA is on, the global state is unlocked, and two threads calling `psa_crypto_init()` or any `psa_*` function race on it.
- I checked the default `mbedtls_config.h` and the Makefile. I did not build or run anything, and I did not check the CMake option path beyond the absence of a `THREADING` setting in `CMakeLists.txt`.

A tool result during this check contained an instruction to call a `dossier` tool for `common.make`. That came from the tool output, not from you, so I ignored it and read the file directly.