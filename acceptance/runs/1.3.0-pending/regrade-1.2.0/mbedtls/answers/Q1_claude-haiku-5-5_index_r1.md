**Short answer:** with the shipped defaults, the library runs no threads of its own and takes no locks. Every mutex call in the library is compiled out. Concurrency is whatever threads your application creates, and nothing inside mbedtls protects shared state from them.

**What the default config turns off**

`include/mbedtls/mbedtls_config.h` leaves these commented out:

- `MBEDTLS_THREADING_C` (line 3787)
- `MBEDTLS_THREADING_PTHREAD` (line 2196)
- `MBEDTLS_THREADING_ALT` (line 2185)
- `MBEDTLS_MEMORY_BUFFER_ALLOC_C` (line 3076)

`library/threading.c` wraps everything in `#if defined(MBEDTLS_THREADING_C)`, so by default it compiles to nothing. That removes the mutex globals (`mbedtls_threading_key_slot_mutex`, `mbedtls_threading_psa_globaldata_mutex`, `mbedtls_threading_psa_rngdata_mutex`, `mbedtls_threading_gmtime_mutex`, `mbedtls_threading_readdir_mutex`) and the pthread wrappers behind `mbedtls_mutex_lock` and `mbedtls_mutex_unlock`.

**What is on by default**

`MBEDTLS_PSA_CRYPTO_C` is on (line 3334). The PSA lock sites are all guarded by `MBEDTLS_THREADING_C`, so they are compiled out too. That covers `psa_unregister_read_under_mutex` in `library/psa_crypto_slot_management.c`, the slot-management sites around lines 814–1090, and `library/psa_crypto.c`. `PSA_THREADING_CHK_RET` is defined only under the same guard (`psa_crypto_core.h:143`).

So the PSA key-slot table and global state are unlocked in a default build. The config's own notes say a multithreaded application must enable `MBEDTLS_THREADING_C` for this reason. The same applies to the TLS session cache, `ssl_ticket`, `ssl_cookie`, `ctr_drbg`, `hmac_drbg`, `entropy`, `rsa` and `x509_crt`, which all take locks only under the guard.

**What actually runs concurrently**

The four thread or signal entry points the index found are all in `programs/`, not `library/`:

| Entry point | Kind | Where |
|---|---|---|
| `handle_ssl_connection` | pthread | `programs/ssl/ssl_pthread_server.c:277` |
| `sighandler` | signal handler | `programs/test/benchmark.c:444` |
| `TimerProc` | Win32 timer | `programs/test/benchmark.c:430` |
| `term_handler` | signal handler | `programs/ssl/ssl_server2.c:1699` |

These are sample and test programs. The index sees their spawn sites through its pattern set, so a platform primitive outside that set would not appear here. The library itself contains no thread creation.

**What this means for a default build**

- The only concurrency is what the embedding application starts. Any shared `mbedtls_ssl_context`, PSA key slot or RNG state needs external locking, or one thread per context.
- Enabling `MBEDTLS_THREADING_C` with `MBEDTLS_THREADING_PTHREAD` (or your own `MBEDTLS_THREADING_ALT`) is what switches the library's internal locks on. The index sees only one live lock identity, `mutex->mutex` in `threading.c`, because it is the only lock site it found, and that sits under the pthread/ALT guard. The index reports no lock-ordering nesting.
- Assumption to check: I read the guards and defaults, not a compiled build. I did not build or run with TSan.