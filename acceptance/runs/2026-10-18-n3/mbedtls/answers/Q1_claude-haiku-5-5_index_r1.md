**Short answer:** in the default configuration, the library starts no threads, takes no locks, and protects nothing. Any concurrency comes from the application calling into the library from several threads.

**Why the defaults compile the locking out**

- `include/mbedtls/mbedtls_config.h:3787` has `//#define MBEDTLS_THREADING_C`, commented out. `MBEDTLS_THREADING_PTHREAD` (line 2196) and `MBEDTLS_THREADING_ALT` (line 2185) are also commented out.
- `library/threading.c:18` wraps the whole file in `#if defined(MBEDTLS_THREADING_C)`, so by default it defines no mutex type, no mutex globals and no function pointers.
- Every mutex call site in the library is guarded by `#if defined(MBEDTLS_THREADING_C)`. That covers `ssl_cache.c`, `ssl_ticket.c`, `ssl_cookie.c`, `entropy.c`, `ctr_drbg.c`, `hmac_drbg.c`, `rsa.c`, `memory_buffer_alloc.c`, `x509_crt.c`, `platform_util.c` and the PSA files. Those calls disappear from the default build.

**What runs concurrently**

- **Library:** nothing. The library creates no threads.
- **Application threads:** the index finds four spawn sites, all in sample and test programs, none in `library/`:
  - `programs/ssl/ssl_pthread_server.c:277`, a pthread per connection running `handle_ssl_connection`
  - `programs/test/benchmark.c:430` and `:444`, a timer thread and a signal handler for the alarm
  - `programs/ssl/ssl_server2.c:1699`, a signal handler (`term_handler`)

**What is not protected by default**

- PSA is on by default (`mbedtls_config.h:3334`), so `global_data` in `library/psa_crypto.c` is shared and unlocked in the default build. The header says that PSA calls from multiple threads need `MBEDTLS_THREADING_C` unless only one thread ever calls PSA (`psa_crypto.h` note, `include/mbedtls/mbedtls_config.h:3314`).
- `MBEDTLS_FS_IO` is on by default (line 1186), but the readdir mutex it implies only exists when threading is on.
- Context objects (SSL caches, DRBG and entropy contexts, RSA contexts) have no internal locking in the default build.

**If `MBEDTLS_THREADING_C` is enabled, what each lock protects** (from `include/mbedtls/threading.h` and the call sites)

| Lock | Protects | Where |
|---|---|---|
| Per-context `ctx->mutex` | That context's state during seed, generate, lookup and store. Used by `ctr_drbg`, `hmac_drbg`, `entropy`, `rsa`, `ssl_cache`, `ssl_ticket`, `ssl_cookie`. | e.g. `library/ssl_cache.c:84`, `library/entropy.c:93` |
| `mbedtls_threading_readdir_mutex` | Directory reads in the x509 load-directory path | `library/x509_crt.c:1611` |
| `mbedtls_threading_gmtime_mutex` | The `gmtime()` call, only when `gmtime_r` is unavailable | `library/platform_util.c:189` |
| `mbedtls_threading_key_slot_mutex` | Key slot state and reader registration | `threading.h:137-144`, `library/psa_crypto.c:1310` and others |
| `mbedtls_threading_psa_globaldata_mutex` | PSA `global_data`, excluding the RNG | `library/psa_crypto.c:141,159` |
| `mbedtls_threading_psa_rngdata_mutex` | PSA RNG state | `library/psa_crypto.c:131`, `:8030` |

**Caveats**

- The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` set as flags, and it has no config header recorded. It cannot answer the default question. I read `mbedtls_config.h` directly.
- The index reports one lock identity (`mutex->mutex` in `threading.c`). That undercounts, because the per-context mutexes are member expressions the index does not model.
- I did not check the build system (CMake or Makefile) for `-D` flags. If the build passes `-DMBEDTLS_THREADING_C -DMBEDTLS_THREADING_PTHREAD`, the table above applies instead of the default picture.