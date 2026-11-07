**Short answer:** by default, mbedtls calls the C library's `calloc`/`free`, but the call sites go through `mbedtls_calloc()` and `mbedtls_free()`, so a project can redirect them at build time or at run time. The library also ships its own allocator that uses this same hook. I answered from the index only, so I could not read the `#if` expressions that select between the paths. Those details are marked below.

**What gets called**

Every allocation in the library goes through the `mbedtls_calloc` / `mbedtls_free` name, never `calloc` / `free` directly. Which function that name reaches depends on configuration:

- **Default (`MBEDTLS_PLATFORM_MEMORY` off):** `include/mbedtls/platform.h:167` defines `mbedtls_calloc` as a plain macro for `calloc`, and `:166` does the same for `free`. The call compiles straight to libc, with no indirection.
- **`MBEDTLS_PLATFORM_MEMORY` on:** `platform.h` maps the names to `MBEDTLS_PLATFORM_CALLOC_MACRO` / `MBEDTLS_PLATFORM_FREE_MACRO` (lines ~138–145), and `library/platform.c:47-55` defines `mbedtls_calloc()` and `mbedtls_free()` as thin forwarders through two static function pointers, `mbedtls_calloc_func` and `mbedtls_free_func` (`platform.c:44-45`). Both pointers are initialised to `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. The index does not show the expansion of those two symbols, so I cannot confirm they resolve to libc. The `component_test_psa_crypto_without_heap` test script sets `MBEDTLS_PLATFORM_STD_CALLOC`/`STD_FREE` to `NULL`, which is how it builds a library that cannot call libc heap functions.

**How a project substitutes its allocator**

Two routes, one per row:

| Route | Mechanism | Where |
|---|---|---|
| Compile time | Enable `MBEDTLS_PLATFORM_MEMORY` and define `MBEDTLS_PLATFORM_CALLOC_MACRO` / `MBEDTLS_PLATFORM_FREE_MACRO` in the config. Test config `tests/configs/user-config-malloc-0-null.h` exercises this. | `platform.h` macros |
| Run time | Call `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)`. It stores both pointers and returns 0. | `library/platform.c:57-63` |

Caveats from the code:
- The setter does not check for `NULL`. Passing `NULL` is accepted, and the next allocation will crash.
- It writes two unguarded globals, so the call must happen before any threads start.
- The two macro symbols have no definition site in the index, which means the shipped default is off. The header named in `config_header` would confirm that.

**What the library does with the facility itself**

`library/memory_buffer_alloc.c` is the library's own allocator. `mbedtls_memory_buffer_alloc_init(buf, len)` (`:566-600`) zeroes a static `heap` context, then calls `mbedtls_platform_set_calloc_free(...)` to install its own functions in place of libc. With `MBEDTLS_THREADING_C` it installs `buffer_alloc_calloc_mutexed` / `buffer_alloc_free_mutexed`, which lock the heap mutex around `buffer_alloc_calloc`. Without it, it installs the unlocked versions. Its header says the allocator "does not call calloc() and free()". So the library's allocator is the same hook a project would use, and it claims the global pointers when initialised.

Consequences:
- Because the heap context is a single static, only one buffer heap exists at a time.
- After `mbedtls_memory_buffer_alloc_init`, a project that also calls `mbedtls_platform_set_calloc_free` will overwrite the buffer allocator.