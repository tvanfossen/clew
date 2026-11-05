**Short answer:** in the default build, the library takes no mutexes at all, and nothing inside it is designed to run concurrently. The mutex and thread code only compiles when you enable `MBEDTLS_THREADING_C` plus an implementation, and the default config doesn't.

**Default config**

- `MBEDTLS_THREADING_C` is commented out (`include/mbedtls/mbedtls_config.h:3787`). `MBEDTLS_THREADING_PTHREAD` and `MBEDTLS_THREADING_ALT` are also off (lines 2185 and 2196).
- `library/threading.c` is wrapped entirely in `#if defined(MBEDTLS_THREADING_C)`, so it compiles to nothing. The `mbedtls_mutex_*` function pointers and the global mutexes don't exist.
- Every lock site I checked is guarded by `MBEDTLS_THREADING_C`: entropy, CTR_DRBG, HMAC_DRBG, the SSL session cache, tickets and cookies, the buffer allocator, PSA, and `gmtime`.
- So with defaults, the library has no locking. Its own docs say the same: `ssl_cache.h` marks functions "Thread-safe if MBEDTLS_THREADING_C is enabled".

**What actually runs concurrently by default**

The only threads in the repository are in `programs/`, not in `library/`. The index finds four spawn sites, all first-party:

| Spawn site | Kind | Role |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` | pthread | one thread per accepted connection, running `handle_ssl_connection` |
| `programs/test/benchmark.c:430` | Win32 timer | `TimerProc`, the alarm used for timing |
| `programs/test/benchmark.c:444` | signal | `sighandler`, the alarm handler |
| `programs/ssl/ssl_server2.c:1699` | signal | `term_handler`, a termination handler |

If a program shares a context (a session cache, ticket context, or RNG) across its pthreads, nothing serialises access. I did not check whether `ssl_pthread_server` shares any such object. The signal handlers run asynchronously against the main code, and no library state is protected from them.

**What is protected when you enable `MBEDTLS_THREADING_C`**

Enabling it means choosing exactly one implementation (`check_config.h:1007`). With pthreads, these are the protected items:

- **Process-global state (`threading.c`):**
  - `mbedtls_threading_readdir_mutex` (`MBEDTLS_FS_IO`): the readdir path. I saw the declaration only.
  - `mbedtls_threading_gmtime_mutex` (non-POSIX builds): guards the fallback `gmtime` path in `platform_util.c:189–201`.
  - `mbedtls_threading_key_slot_mutex` (PSA): protects the key-slot table. It is held across destroy (`psa_crypto.c:1310`), create and load (`1801`, `1927`), and slot wipe (`2022`).
  - `mbedtls_threading_psa_globaldata_mutex` (PSA): protects the initialisation flags (`psa_crypto.c:141–165`).
  - `mbedtls_threading_psa_rngdata_mutex` (PSA): protects RNG state (`psa_crypto.c:8030–8083`, `8384–8396`). The comments at `7982` and `7996` say the caller must already hold it.
- **Per-object mutexes:** each object guards its own state with one mutex, taken and released inside one function body.
  - Entropy context: `entropy.c:93, 179, 254, 294`
  - CTR_DRBG: `ctr_drbg.c:703`
  - HMAC_DRBG: `hmac_drbg.c:388`
  - SSL session cache: `ssl_cache.c:84, 259, 331`
  - SSL tickets: `ssl_ticket.c:330, 445`
  - SSL cookies: `ssl_cookie.c:249, 332`
  - Heap allocator: `memory_buffer_alloc.c:540–564`, which wraps calloc and free on `heap.mutex`.
- **Lock nesting:** the index reports zero two-lock holdings, so no critical section calls into code that takes a second lock. That is a database result, not a deadlock-freedom proof.

**Caveats**

- The index's lock layer shows one identity, `mutex->mutex` in `threading.c`. The library calls go through function pointers (`mbedtls_mutex_lock` is a variable), so the index doesn't attribute the per-object and PSA locks to their objects. The list above comes from reading the source with grep, not from the index.
- Everything here is static reading. I did not build with `MBEDTLS_THREADING_C` enabled or run any test under threads.