**Short answer:** by default, every mbedtls allocation is a plain `calloc`/`free` from libc. The library never calls those directly. It calls `mbedtls_calloc` and `mbedtls_free`, and what those resolve to depends on the build config. A project can swap the allocator at compile time or at runtime.

**Call chain (default-style build, `MBEDTLS_PLATFORM_MEMORY` off)**

```
library code (cipher_wrap.c, md.c, ecp.c, pk_wrap.c, ...)
   └─ mbedtls_calloc(n, sz)  ──macro──>  calloc(n, sz)   (include/mbedtls/platform.h ~167)
      mbedtls_free(p)       ──macro──>  free(p)
```

Per the index, `mbedtls_calloc` has about 147 callers and `mbedtls_free` about 133. Calls into the library go through the macro names, not libc.

**Substitution, option 1: compile-time (`MBEDTLS_PLATFORM_MEMORY`)**

- Enable `MBEDTLS_PLATFORM_MEMORY` (default off, `mbedtls_config.h:208`).
- Define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in your user config, so `mbedtls_calloc`/`mbedtls_free` expand to your functions (`platform.h` ~139–145).
- The repo's test config does this with a simpler mapping. `tests/configs/user-config-malloc-0-null.h` defines `MBEDTLS_PLATFORM_STD_CALLOC` as `custom_calloc`, which returns NULL for zero-size requests and otherwise calls libc `calloc`.

**Substitution, option 2: runtime**

- Call `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)` (`library/platform.c:57-63`). It assigns two file-static function pointers, `mbedtls_calloc_func` and `mbedtls_free_func`. Those pointers default to `MBEDTLS_PLATFORM_STD_CALLOC` and free. The function body does no locking and no check for prior calls, so call it before the library starts allocating or running threads.
- `mbedtls_calloc` and `mbedtls_free` (`platform.c:47-55`) are thin wrappers that dereference those pointers.

**What the library does with the facility**

- **Ownership:** every internal allocation goes through `mbedtls_calloc`. Examples: the `ALLOC` macro in `md.c`, and the `*_ctx_alloc` functions in `cipher_wrap.c`.
- **Zeroize-then-free:** `mbedtls_zeroize_and_free` (`platform_util.c:139-146`) wipes the buffer, then calls `mbedtls_free`. Many key and context free paths use it, including RSA, DHM and LMS.
- **Built-in allocator:** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) lets a caller hand the library a fixed buffer. It installs its own `buffer_alloc_calloc` and `buffer_alloc_free` through `mbedtls_platform_set_calloc_free`. With `MBEDTLS_THREADING_C` it uses mutex-wrapped variants (`buffer_alloc_calloc_mutexed`, which locks around the inner call). The allocator never calls libc. `mbedtls_memory_buffer_alloc_free` tears it down.

**Caveats (what this index does not settle)**

- The index has no definition site for `MBEDTLS_PLATFORM_CALLOC_MACRO` or `FREE_MACRO`. The shipped default is therefore unconfirmed here. Read `mbedtls_config.h` to check.
- The index shows `mbedtls_platform_set_calloc_free` only as a `.c` definition. Its header prototype is not indexed, so I could not confirm the public declaration.
- The `MBEDTLS_PLATFORM_STD_CALLOC` default shows `origin: heuristic` in the index. Treat it as likely, not verified.