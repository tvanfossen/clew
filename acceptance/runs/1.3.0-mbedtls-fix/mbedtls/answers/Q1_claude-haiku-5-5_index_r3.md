**Short answer:** with the default configuration, mbedtls runs no threads of its own and takes no locks. Its mutex code compiles out. The concurrency lives in the example programs, and it is only protected when you opt into `MBEDTLS_THREADING_C`.

**Default build**

- `MBEDTLS_THREADING_C` is commented out in `include/mbedtls/mbedtls_config.h:3787`, so `library/threading.c` compiles to nothing (its body is inside `#if defined(MBEDTLS_THREADING_C)`, line 18).
- Every `mbedtls_mutex_lock/unlock` call site in the library is inside a `#if defined(MBEDTLS_THREADING_C)` guard. Those include `ssl_cache.c`, `ssl_ticket.c`, `ssl_cookie.c`, `rsa.c`, `entropy.c`, `hmac_drbg.c`, `ctr_drbg.c`, `memory_buffer_alloc.c`, `x509_crt.c`, `platform_util.c` and `psa_crypto_slot_management.c`. With the layer off, none of them exist.
- The library itself creates no threads. The only spawn sites the index finds are in `programs/`:

| Spawn site | Kind | Role |
|---|---|---|
| `programs/ssl/ssl_pthread_server.c:277` | pthread | one thread per connection, runs `handle_ssl_connection` |
| `programs/test/benchmark.c:430` | Win32 timer | alarm thread |
| `programs/test/benchmark.c:444` | signal handler | alarm |
| `programs/ssl/ssl_server2.c:1699` | signal handler | `term_handler` |

- The threading documentation (`mbedtls_config.h:3740-3787`) says contexts are assumed unshared between threads unless the layer is enabled.

**Caveat on the index numbers.** The index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` stated as flags, so its lock and spawn results describe a threaded build, not the default. It also has no config header recorded, so it cannot tell you the repository's own default.

**Threaded build (`MBEDTLS_THREADING_C` + `PTHREAD`)**

| What is protected | Lock | Notes |
|---|---|---|
| Session cache entries | per-cache mutex | `ssl_cache.c` lock and unlock around get/set/remove |
| Session ticket keys | per-context mutex | `ssl_ticket.c` |
| Cookie secret | per-context mutex | `ssl_cookie.c` |
| RSA context (blinding and state) | per-context mutex | `rsa.c`, lock and unlock around private operations |
| Entropy pool and sources | per-context mutex | `entropy.c` |
| DRBG state (CTR and HMAC) | per-context mutex | `ctr_drbg.c`, `hmac_drbg.c` |
| Heap allocator | global heap mutex | `memory_buffer_alloc.c`, the `calloc`/`free` wrappers |
| PSA key slots | `mbedtls_threading_key_slot_mutex` | `psa_crypto_slot_management.c` |
| PSA global data | `mbedtls_threading_psa_globaldata_mutex` | same file |
| `gmtime` fallback | global mutex | `platform_util.c`, only when `gmtime_r` is unavailable |
| `readdir` (CRL/CA directory loading) | global mutex | `x509_crt.c` |

The mutex operations are function pointers (`threading.c:101-104`), so you can swap in your own implementation with `MBEDTLS_THREADING_ALT`.

**Things I did not settle**

- The index reports one lock identity (`mutex->mutex`) and zero nested holdings. Those numbers are not a mutex count: the index does not model member-expression lock operands, so most of the table above is from reading source, not from the index.
- I did not verify lock ordering between the two PSA mutexes. The zero-nesting result is the index's, not a proof of deadlock freedom.
- The header says a TLS 1.3 connection needs the layer "regardless of the compile-time configuration". That is the documented requirement; I did not trace where it is enforced in code.