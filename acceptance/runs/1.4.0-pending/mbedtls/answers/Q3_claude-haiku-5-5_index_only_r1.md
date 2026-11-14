**Short answer:** every library allocation goes through `mbedtls_calloc()` / `mbedtls_free()`. What those resolve to depends on the build configuration, and the library's own stack-based allocator is one of the things that can sit behind them.

**What gets called, by configuration** (the index doesn't know the repo's own config header, so shipped defaults are inferred and should be checked against `mbedtls_config.h`):

```
MBEDTLS_PLATFORM_MEMORY off (default)
  mbedtls_calloc()  --macro, platform.h:167-->  calloc()          (no indirection)

MBEDTLS_PLATFORM_MEMORY on, no macros
  mbedtls_calloc()  --platform.c:47-->  mbedtls_calloc_func  --> calloc()
                                        (static ptr, platform.c:44,
                                         initialised to MBEDTLS_PLATFORM_STD_CALLOC)

MBEDTLS_PLATFORM_MEMORY on, CALLOC/FREE_MACRO defined
  mbedtls_calloc()  --platform.h:144-->  <your macro>             (compile-time, no pointer)
```

`mbedtls_free()` mirrors this with `mbedtls_free_func` (platform.c:45) and `MBEDTLS_PLATFORM_FREE_MACRO`.

**How a project substitutes its allocator** — two options:

1. **Compile time.** Set `MBEDTLS_PLATFORM_MEMORY` in the user config and define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` to your functions. The header documents this as the path that avoids a runtime pointer. `tests/configs/user-config-malloc-0-null.h` is an in-repo example.
2. **Runtime.** Set only `MBEDTLS_PLATFORM_MEMORY` and call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any allocation. The body (platform.c:57-63) just stores the two pointers. It has no NULL check and no lock, so swapping allocators while other threads are allocating is a race. Do it during init.

**What the library does with the facility:**

- **Call sites.** The index shows the `mbedtls_` wrappers used throughout: cipher context allocation (`cipher_wrap.c`), PK/RSA/EC wrappers (`pk_wrap.c`), bignum growth (`bignum.c`), SSL sessions and handshake buffers (`ssl_tls.c`), PSA key and operation buffers (`psa_crypto.c`), X.509 parsing (`x509_crt.c`, `x509_crl.c`), PEM and OID. Frees go through `mbedtls_free`.
- **Zeroize-then-free.** `mbedtls_zeroize_and_free()` (`platform_util.c:139`) zeroizes the buffer, then calls `mbedtls_free()`. Key material and session state use it.
- **Its own allocator.** `mbedtls_memory_buffer_alloc_init()` (`memory_buffer_alloc.c:566`) is the library's one in-tree user of `mbedtls_platform_set_calloc_free()`. It aligns and zeroes a caller-supplied buffer, builds a heap from it, and installs its own calloc/free pair: the mutexed variants when `MBEDTLS_THREADING_C` is on. After that, every library allocation draws from that buffer. The heap is a single global, so there is one per process.

**Caveats from the index:**

- Config defaults are inferred from line numbers, not read from a declared config header.
- The index shows no application in the repo calling `mbedtls_platform_set_calloc_free` itself; the only caller found is the memory-buffer allocator. `programs/test/benchmark.c` calls `mbedtls_memory_buffer_alloc_init`.
- I did not check for a matching `mbedtls_memory_buffer_alloc_free`, or how the heap behaves under exhaustion.