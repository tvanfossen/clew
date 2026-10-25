## What gets called

Every allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`. Library code calls these names directly, for example `aes_ctx_alloc`, `mbedtls_md_setup`, the SSL and X.509 parsers, and the PSA helpers. Which function actually runs depends on the build.

**Runtime path (function pointers), the default-style route in `library/platform.c`:**

```
library code
  -> mbedtls_calloc(n, size)        platform.c:47
     -> (*mbedtls_calloc_func)()    static pointer, platform.c:44
        initialised to MBEDTLS_PLATFORM_STD_CALLOC  (platform.h:124, libc calloc)

  -> mbedtls_free(p)                platform.c:52
     -> (*mbedtls_free_func)()      platform.c:45, initialised to MBEDTLS_PLATFORM_STD_FREE
```

**Compile-time path (macros), `include/mbedtls/platform.h`:**

- When `MBEDTLS_PLATFORM_MEMORY` is set, `mbedtls_calloc` and `mbedtls_free` are macros that expand to `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` (lines 138–145). The call is then redirected at preprocessing time and no function pointer is involved.
- The index shows the header's `mbedtls_calloc` at line 167 expanding to plain `calloc`, gated by `MBEDTLS_PLATFORM_MEMORY` at line 163. I read that as the non-`MEMORY` case, but the index does not confirm it.

## How a project substitutes its allocator

Two options, which the library supports together:

1. **Compile time.** Define `MBEDTLS_PLATFORM_MEMORY` and point `MBEDTLS_PLATFORM_CALLOC_MACRO` / `MBEDTLS_PLATFORM_FREE_MACRO` at your functions in your config header. The test config `tests/configs/user-config-malloc-0-null.h` does this: it sets `MBEDTLS_PLATFORM_STD_CALLOC` to `custom_calloc` (line 21). Nothing in the library then calls libc.
2. **Run time.** Call `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)` (`platform.c:57-63`). It assigns the two static pointers and returns 0. It has no locking and no validation, so the swap must happen before any allocation is made.

If you want no libc at all, `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` removes the standard defaults. The index shows the standard calloc slot then resolving to `platform_calloc_uninit` (`platform.c:32`). I did not read that body, so I can't say what it does at runtime.

## What the library itself does with the facility

The library ships one allocator built on this hook: a fixed-buffer heap in `library/memory_buffer_alloc.c`.

- `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) zeroes a static heap context and calls `mbedtls_platform_set_calloc_free`. It installs `buffer_alloc_calloc_mutexed` when `MBEDTLS_THREADING_C` is on, otherwise `buffer_alloc_calloc`. It then aligns the buffer and writes the first block header with magic values.
- The mutexed variant wraps `buffer_alloc_calloc` in a mutex lock and unlock (`memory_buffer_alloc.c:541-552`).
- The library never calls this init itself. Its only caller in the index is `main`, so the application opts in.

Two things to check in that init:

- If `len` is too small, the function returns early. By then it has already installed the allocator pointers, but `heap.first` is still NULL. I did not read `buffer_alloc_calloc`, so I can't say whether a later allocation would crash or return NULL.
- The index does not show a lock on `mbedtls_platform_set_calloc_free`. Swapping allocators while other threads allocate is therefore unsafe. This is my inference from the code, not something the index states.

## Gaps in the index

- The shipped default for `MBEDTLS_PLATFORM_MEMORY` and the `CALLOC_MACRO` family is not answerable. No `config_header` is recorded, and the index has no definition site for `MBEDTLS_PLATFORM_CALLOC_MACRO` or `FREE_MACRO`.
- `platform_calloc_uninit` and `buffer_alloc_calloc` bodies were not read.