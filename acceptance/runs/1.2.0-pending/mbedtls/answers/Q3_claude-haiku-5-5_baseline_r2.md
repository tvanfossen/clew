**Short answer:** mbedtls never calls `calloc` or `free` directly in its own code. Every allocation goes through `mbedtls_calloc` and every release through `mbedtls_free`. What those two names resolve to depends on the build configuration: the C library by default, a compile-time macro, or a runtime function pointer that the project sets.

**What gets called**

The library has 48 files that call `mbedtls_calloc` and 188 `mbedtls_free` call sites. Raw `calloc`/`free` appear only in comments. Resolution depends on three configuration cases:

| Config | What `mbedtls_calloc` / `mbedtls_free` become | Where |
|---|---|---|
| `MBEDTLS_PLATFORM_MEMORY` undefined | `#define`d straight to `calloc` / `free` | `include/mbedtls/platform.h`, `#else` branch near line 180 |
| `MBEDTLS_PLATFORM_MEMORY` plus both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | `#define`d to your functions at compile time. No runtime indirection, and `mbedtls_platform_set_calloc_free` is compiled out. | `platform.h` (the `#if ... FREE_MACRO && CALLOC_MACRO` branch) and the guard in `library/platform.c:21` |
| `MBEDTLS_PLATFORM_MEMORY` only | Real functions in `library/platform.c:47-54` that call through two global function pointers. The pointers start at `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE`. | `library/platform.c:44-62` |

The default for the last row is `calloc`/`free` when `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is off. When that option is on, the default is a stub that returns NULL from calloc and does nothing on free, so the project must supply its own functions before the library allocates. (`mbedtls_config.h` around lines 165-202 documents this.)

**How a project substitutes its allocator**

- **Compile-time (preferred for embedded):** in its config, define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free`. Both macros must be set together. This has no runtime cost and no registration step.
- **Compile-time, default-plus-override:** define `MBEDTLS_PLATFORM_MEMORY` and `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE` instead. `tests/configs/user-config-malloc-0-null.h` does this with a `custom_calloc` that returns NULL for zero-size requests.
- **Runtime:** define only `MBEDTLS_PLATFORM_MEMORY`, then call `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)` before any library call that allocates. It stores the two pointers and returns 0. It does no validation.

The header comment says the function-pointer choice is made at runtime, but it does not require any locking.

**What the library does with the facility**

- **Its own allocator.** `library/memory_buffer_alloc.c` is a first-fit heap built over a caller-supplied byte buffer. `mbedtls_memory_buffer_alloc_init(buf, len)` calls `mbedtls_platform_set_calloc_free(...)` itself, so initialising it installs the heap as the process-wide allocator. When `MBEDTLS_THREADING_C` is enabled it installs mutex-wrapped variants. The heap is a single static `heap` context, not per-instance.
- **Wipe-then-free.** 75 call sites use `mbedtls_zeroize_and_free(buf, len)` (`library/platform_util.c`). It zeroizes non-NULL buffers and then calls `mbedtls_free`, so the free function must accept NULL.
- **Dependency on pairing.** Whatever free function is installed must release what the matching calloc returned. The header states that only pointers from `MBEDTLS_PLATFORM_STD_CALLOC` are passed to `MBEDTLS_PLATFORM_STD_FREE`.

**Caveats I inferred from the code (not tested)**

- The two function pointers are plain globals with no synchronisation. Swapping the allocator while another thread is allocating, or while live blocks from the old allocator exist, is unsafe unless the new free can handle the old pointers. The code gives no guidance on this, so set the allocator once at startup.
- In the mutex-wrapped heap free, if the lock fails the function returns without freeing (`buffer_alloc_free_mutexed`). The comment says losing memory is preferred to corrupting the heap, so a lock failure leaks.