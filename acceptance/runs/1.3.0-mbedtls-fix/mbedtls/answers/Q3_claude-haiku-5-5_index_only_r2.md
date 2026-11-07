**Short answer:** library code never calls `calloc`/`free` directly. It calls `mbedtls_calloc` and `mbedtls_free`, which are thin wrappers that forward through two global function pointers. Those pointers default to the C standard functions and can be replaced at runtime or at build time.

**The call chain**

```
library code (cipher_wrap.c, bignum.c, ssl_tls.c, psa_crypto.c, ...)
  -> mbedtls_calloc(n, size)           library/platform.c:47
       -> (*mbedtls_calloc_func)(n, size)
  -> mbedtls_free(ptr)                 library/platform.c:52
       -> (*mbedtls_free_func)(ptr)
```

- `mbedtls_calloc_func` is a `static` function pointer at `library/platform.c:44`, initialised to `MBEDTLS_PLATFORM_STD_CALLOC`. That macro expands to `calloc` when the standard functions are enabled.
- `platform_calloc_uninit` (`platform.c:25`) is the fallback that always returns NULL. It is selected when `MBEDTLS_PLATFORM_STD_CALLOC` is not defined.
- The index shows about 40 library call sites of `mbedtls_calloc`, including the context allocators in `cipher_wrap.c`, `bignum.c`, `pkwrite.c` and `ssl_tls.c`. The only direct `calloc` in `library/` is the default in `platform.c`.

**Build-time selection**

The public header `include/mbedtls/platform.h` picks the names by configuration:

| Configuration | `mbedtls_calloc` / `mbedtls_free` expand to |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` undefined (`platform.h:163-168`) | plain `calloc` / `free` |
| `MBEDTLS_PLATFORM_MEMORY` defined (`platform.h:138-163`) | `MBEDTLS_PLATFORM_CALLOC_MACRO` / `MBEDTLS_PLATFORM_FREE_MACRO` (`platform.h:143-144`) |

The index shows that `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` have no definition site in the repository. That is expected: a project supplies them itself.

**How a project substitutes its allocator**

There are two routes, and they can be combined:

1. **Compile-time macros.** Set `MBEDTLS_PLATFORM_MEMORY` in the project's config header (`MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` are the substitutes). The `tests/configs/user-config-malloc-0-null.h` fixture is an example of this route. With `MBEDTLS_PLATFORM_MEMORY` set, `platform.c:20-64` compiles without the standard fallback.
2. **Runtime function pointers.** Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (`platform.c:57-63`). It stores the two pointers and returns 0. The mbedtls allocator then routes through them for the rest of the process.

**What the library does with the facility itself**

`mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566-600`) is the library's own user of this mechanism. It:

- sets up a heap over a caller-supplied buffer, with a mutex when `MBEDTLS_THREADING_C` is on;
- calls `mbedtls_platform_set_calloc_free(buffer_alloc_calloc_mutexed, buffer_alloc_free_mutexed)` (or the non-mutexed pair), so every later `mbedtls_calloc` and `mbedtls_free` allocates from that buffer and never reaches libc.

So the same hook serves both purposes: a project's own allocator, or the built-in static-buffer allocator.

**Caveats**

- The pointers are plain globals. Swapping them while other threads are inside mbedtls is unsafe. The index's notes on `mbedtls_memory_buffer_alloc_init` say only that the allocator functions are thread-safe when `MBEDTLS_THREADING_C` is defined.
- The index's `MBEDTLS_PLATFORM_STD_CALLOC` config default reads "off" with origin "heuristic". Treat the standard-function default as inferred from the platform header, not as verified from the shipped config.
- I did not read the preprocessor blocks in `platform.h` line by line. The mapping above comes from the index's macro expansions and gate records.