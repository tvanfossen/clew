**Short answer:** in the default configuration, the library runs no concurrent work of its own and takes no locks. The only threads in the repository are in `programs/`. The mutex code is compiled out, so nothing in the library is protected. Callers must serialize access themselves.

**Why the default is lock-free**

- `include/mbedtls/mbedtls_config.h:3787` has `//#define MBEDTLS_THREADING_C` commented out, and `MBEDTLS_THREADING_PTHREAD` (line 2196) is also off.
- Every mutex use in `library/` is wrapped in `#if defined(MBEDTLS_THREADING_C)`, so none of it is compiled by default.
- Nothing in the build (CMake, Makefile, `library/Makefile`) turns it on.
- `library/threading.c:18` wraps the whole file in that guard. With it off, the file contributes nothing.

**What runs concurrently**

| Context | Where | Default build? |
|---|---|---|
| Library code | `library/` | Runs in whatever threads the caller uses. The library creates none. |
| `handle_ssl_connection`, one pthread per connection | `programs/ssl/ssl_pthread_server.c:277` | Example server only |
| `sighandler`, `term_handler`, `TimerProc` | `programs/test/benchmark.c`, `programs/ssl/ssl_server2.c` | Example and test programs only |

The index found four spawn sites, all in `programs/`, and none in `library/`.

**What the mutexes protect when `MBEDTLS_THREADING_C` is on**

These are per-object mutexes, initialized in each `*_init` and freed in each `*_free`:

- **Context state:** `ssl_cache.c` (session cache), `ssl_ticket.c` (ticket keys), `ssl_cookie.c`, `rsa.c` (the RSA context), `entropy.c`, `ctr_drbg.c`, `hmac_drbg.c`. Each guards that one context's state during lock/unlock pairs.
- **Heap:** `memory_buffer_alloc.c:540–571` uses `heap.mutex` around the allocator.
- **Process-wide globals:**
  - `mbedtls_threading_gmtime_mutex` in `platform_util.c:188` serializes the `gmtime` fallback.
  - `mbedtls_threading_readdir_mutex` in `x509_crt.c:1610` serializes directory reads.
  - `mbedtls_threading_key_slot_mutex`, `mbedtls_threading_psa_globaldata_mutex` and `mbedtls_threading_psa_rngdata_mutex` in `psa_crypto.c` and `psa_crypto_slot_management.c` protect PSA key slots, PSA global state and the PSA RNG.

These are defined in `library/threading.c:182–190`. Their function pointers default to pthread (`threading.c:101–104`). With `MBEDTLS_THREADING_ALT`, the defaults fail on lock (`threading.c:127–128`), so a custom implementation must be installed with `mbedtls_threading_set_alt()`.

**The gap in the default build**

`MBEDTLS_PSA_CRYPTO_C` is enabled by default (`mbedtls_config.h:3334`). So the PSA global state (key slots, the RNG state in `psa_crypto_random.c`, global data in `psa_crypto.c`) is shared and mutable, but it is unlocked in the default build. The header comments say a multithreaded application must enable `MBEDTLS_THREADING_C` (`mbedtls_config.h:1878`, `2213`, `3314`). Calling `psa_*` functions from more than one thread without it is a data race. I did not find a default-build lock anywhere in the PSA path.

**Caveats on the index**

- The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` predefined (`preprocessor.explicit`). Its lock and thread layers therefore describe the threaded build, not the default.
- The lock layer shows one identity, `mutex->mutex` in `threading.c`. That is a member access reached through function pointers, so the index could not enumerate the per-context mutexes. I got the list above from grep.
- `dossier` on `mbedtls_mutex_lock` showed no callers because the call sites go through a function pointer. I used grep for those.