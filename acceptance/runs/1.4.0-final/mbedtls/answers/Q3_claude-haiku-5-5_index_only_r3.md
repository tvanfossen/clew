The library never calls `malloc` or `calloc` directly. Every allocation goes through `mbedtls_calloc()` and `mbedtls_free()`, and those dispatch through either a runtime function-pointer pair or a compile-time macro, depending on configuration. This is from the index only; I did not read the source text beyond what the index returned.

**Call path**

```
library code (e.g. mbedtls_mpi_grow, cipher ctx_alloc, pk_wrap, ecp)
   │
   ▼
mbedtls_calloc(n, size)            library/platform.c:47
   │   return (*mbedtls_calloc_func)(n, size);
   ▼
mbedtls_calloc_func                library/platform.c:44 (static pointer)
   │   initialised to MBEDTLS_PLATFORM_STD_CALLOC
   ▼
user function, or libc calloc
```

`mbedtls_free()` is the same shape, through `mbedtls_free_func` (platform.c:45 and 52–55).

**Compile-time branch (`include/mbedtls/platform.h`)**

- When `MBEDTLS_PLATFORM_MEMORY` is on, `mbedtls_calloc` and `mbedtls_free` become macros (platform.h:138–168). If `MBEDTLS_PLATFORM_CALLOC_MACRO` / `MBEDTLS_PLATFORM_FREE_MACRO` are also defined, they expand to the user's functions. Otherwise they expand to plain `calloc` / `free`.
- When `MBEDTLS_PLATFORM_MEMORY` is off, the library uses the function-pointer dispatch above.
- `MBEDTLS_PLATFORM_MEMORY` defaults to off (`include/mbedtls/mbedtls_config.h:208`). The two `*_MACRO` symbols have no definition site in the index, so they are set by the user's config, not by the shipped header.

**Default pointer**

`mbedtls_calloc_func` is initialised to `MBEDTLS_PLATFORM_STD_CALLOC` (platform.c:44). If that macro is not defined, the index shows a static fallback, `platform_calloc_uninit`, which always returns NULL (platform.c:25–33). My reading is that a build with no standard functions and no setter call fails every allocation. I did not confirm the exact `#if` wiring in platform.c.

**How a project substitutes its allocator**

Two routes, by build time:

1. **Compile-time, through the config.** Define `MBEDTLS_PLATFORM_MEMORY` and point `MBEDTLS_PLATFORM_CALLOC_MACRO` / `MBEDTLS_PLATFORM_FREE_MACRO` at your functions, or define `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE` to your own calloc and free. `tests/configs/user-config-malloc-0-null.h` does this: `MBEDTLS_PLATFORM_STD_CALLOC` is set to `custom_calloc`, and `MBEDTLS_PLATFORM_MEMORY` is defined in the same file (lines 20–21). The override goes in a user config file that `mbedtls_config.h` picks up.

2. **Runtime, through the setter.** Call `mbedtls_platform_set_calloc_free(calloc_func, free_func)` (platform.c:57–63). It just assigns the two static pointers and returns 0. It does no validation and no locking. Call it before any other library call and before any threads run, because the pointers are plain globals.

**What the library does with the facility itself**

- `mbedtls_memory_buffer_alloc_init(buf, len)` (memory_buffer_alloc.c:566–600) is the library's own allocator. It makes a heap out of a caller-supplied buffer and installs its own `buffer_alloc_calloc` / `buffer_alloc_free` through the same setter. With `MBEDTLS_THREADING_C` it installs the `_mutexed` wrappers, which lock a mutex around each call (memory_buffer_alloc.c:541–552). It aligns the buffer, zeroes it, and writes the first block header with two magic values.
- `mbedtls_memory_buffer_alloc_free()`, `..._verify()`, and the status and max/count getters manage that heap. The self-test (`mbedtls_memory_buffer_alloc_self_test`) also uses it.
- Most library allocations are direct callers of `mbedtls_calloc`: the cipher context constructors in `cipher_wrap.c`, the pk wrap code, `ecp`, `asn1parse`, `lms`, `bignum` (`mbedtls_mpi_grow`), and `md.c`'s `ALLOC` macro. The matching frees go through `mbedtls_free`.

**Caveats**

- The index lists threads that reach these functions (for example, the SSL pthread server in `programs/ssl/ssl_pthread_server.c`). Whether a custom allocator is thread-safe is the project's responsibility. The buffer allocator is thread-safe only with `MBEDTLS_THREADING_C`.
- I did not verify the default value of `MBEDTLS_PLATFORM_STD_CALLOC` in `platform.h` beyond the index's config row, which reports it as off by heuristic.