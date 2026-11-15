**Short answer:** mbedtls never calls `calloc`/`free` directly in its own code. Every allocation goes through two function pointers in `library/platform.c`, and the library ships a stack-buffer allocator that swaps those pointers out.

**What gets called**

```
library code (md.c, cipher_wrap.c, ecp.c, asn1parse.c, ...)
  -> mbedtls_calloc(n, size)  -> (*mbedtls_calloc_func)(n, size)
  -> mbedtls_free(p)          -> (*mbedtls_free_func)(p)
```

- `mbedtls_calloc` and `mbedtls_free` are thin wrappers at `library/platform.c:47-55`. Each one calls through a static function pointer.
- The pointers are `static void *(*mbedtls_calloc_func)(size_t, size_t) = MBEDTLS_PLATFORM_STD_CALLOC;` at `library/platform.c:44`, and the free pointer is set up the same way.
- At compile time, `include/mbedtls/platform.h` decides what the public names expand to. `mbedtls_calloc` expands to `MBEDTLS_PLATFORM_CALLOC_MACRO` when `MBEDTLS_PLATFORM_MEMORY` is enabled (`platform.h:138-145`). Otherwise it is a direct `calloc` (`platform.h:163-168`). I read those gates from the index, not from the header text, so check the `#if` structure there before relying on the exact branch.
- Library call sites use the wrappers, not libc. Examples: the `ALLOC` macro in `library/md.c` calls `mbedtls_calloc`. The `*_ctx_alloc` functions in `library/cipher_wrap.c`, plus `pk_wrap.c`, `ecp.c` and `asn1parse.c`, do the same. Their matching `*_free` paths call `mbedtls_free`.

**Default state of the pointers**

Under the shipped config, `MBEDTLS_PLATFORM_STD_CALLOC` is off (`include/mbedtls/mbedtls_config.h:4124`). In that case the calloc pointer starts as `platform_calloc_uninit` (`library/platform.c:25-30`), which always returns `NULL`. So any allocation fails until something installs an allocator. Allocation can be made to work with the standard functions by defining `MBEDTLS_PLATFORM_STD_CALLOC` (and its free counterpart) yourself. I did not confirm the exact `#if` that selects `platform_calloc_uninit`. The index shows it gated on `MBEDTLS_PLATFORM_STD_CALLOC` inside `platform.c` around lines 20-33.

**How a project substitutes its own allocator**

Two routes, both visible in the index:

1. **Runtime replacement.** Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (`library/platform.c:57-63`). It only assigns the two pointers and returns 0. It does no locking and no NULL checks, so call it once at startup, before any threads start. It is the only thing that writes the pointers, and the only caller in the library is the memory-buffer allocator.
2. **Compile-time replacement.** Enable `MBEDTLS_PLATFORM_MEMORY` and define `MBEDTLS_PLATFORM_CALLOC_MACRO` / `MBEDTLS_PLATFORM_FREE_MACRO` in a user config. This makes `mbedtls_calloc`/`mbedtls_free` expand to your functions directly, with no pointer hop. The index has a test fixture showing this, `tests/configs/user-config-malloc-0-null.h`, which defines `custom_calloc`. I did not read that file.

**What the library does with the facility itself**

- **Stack/buffer allocator.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566-600`) takes a caller-supplied buffer and manages it internally, without calling libc. It installs its own `buffer_alloc_calloc` / `buffer_alloc_free`, or the `_mutexed` variants when `MBEDTLS_THREADING_C` is on, through `mbedtls_platform_set_calloc_free`. It aligns the buffer, zeroes it, and sets up one header covering the whole buffer. `mbedtls_memory_buffer_alloc_free` tears it down. The index also lists `_status`, `_max_get`, `_verify` and `_self_test` helpers for diagnosing that heap.
- **Secure free.** `mbedtls_zeroize_and_free` (`library/platform_util.c:139-146`) zeroes the buffer with `mbedtls_platform_zeroize` and then calls `mbedtls_free`. Context teardown in several modules uses it.
- **Reach.** Because all library allocation funnels through the two wrappers, one substitution covers the whole library. The index shows callers across ciphers, PK, ECP, LMS, ASN.1, PEM, bignum and SSL.

**Caveats**

- The pointers are plain globals with no synchronization, so replacing them while other threads allocate is a race. The index's thread data shows an SSL pthread server (`programs/ssl/ssl_pthread_server.c`) that is the main concurrent user; I did not check whether it installs allocators.
- Each dossier was truncated by the response size cap, so caller lists are partial (for example, `mbedtls_calloc` has 147 callers in total and I saw 36). Nothing above depends on a complete caller list.