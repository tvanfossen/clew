**Short answer:** every allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`. What those resolve to depends on build config. By default that is libc `calloc`/`free`. A project can replace them at compile time with two macros, or at runtime with `mbedtls_platform_set_calloc_free()`. The library's own stack-based buffer allocator uses that same runtime hook.

**Call path**

```
library code: mbedtls_calloc(n, sz) / mbedtls_free(p)
   │
   ├─ MBEDTLS_PLATFORM_MEMORY off ───────────► macro → calloc / free (platform.h:166-167)
   ├─ MEMORY on + CALLOC_MACRO & FREE_MACRO ─► macro → your functions (platform.h:139-145)
   └─ MEMORY on, no macros ──────────────────► real function (platform.c:47-55)
                                                  │ calls through static pointers
                                                  ▼
                          mbedtls_calloc_func / mbedtls_free_func (platform.c:44-45)
                          default: MBEDTLS_PLATFORM_STD_CALLOC/FREE
```

- **Default build:** `platform.h:166-167` maps `mbedtls_calloc` to `calloc` and `mbedtls_free` to `free`, so there is no indirection.
- **Library code is clean.** A grep of `library/` for raw `calloc`/`malloc`/`free` finds nothing outside `platform.c`. The one raw `free` is `memory_buffer_alloc.c:404`, which frees `backtrace_symbols()` output under `MBEDTLS_MEMORY_BACKTRACE`. That memory is libc-allocated, so libc `free` is correct there.

**How a project substitutes its allocator**

1. **Compile time (no runtime layer).** Set `MBEDTLS_PLATFORM_MEMORY`, then define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in your `mbedtls_config.h`. The two must be defined together (`check_config.h:572`). The macros win over any runtime setting, and `platform.c`'s pointer block is compiled out (`platform.c:16-20`).

2. **Runtime.** Set only `MBEDTLS_PLATFORM_MEMORY`, leave the macros undefined, and call once during startup, before any allocation:
   ```c
   mbedtls_platform_set_calloc_free(my_calloc, my_free);
   ```
   The function (`platform.c:57-63`) just stores two global function pointers. It has no locking, so don't swap allocators while other threads are using the library.

   Contract for your functions:
   - `calloc` must zero the memory and return NULL on failure.
   - `free` must accept NULL as a no-op.
   - Every pointer you return must be freeable by your `free`.

**Things that will bite you**

- With `MBEDTLS_PLATFORM_MEMORY` on and no `MBEDTLS_PLATFORM_STD_CALLOC`/`STD_FREE` defined, the default is the stubs in `platform.c:24-42`. `calloc` returns NULL and `free` does nothing until you call the setter. The stubs are only replaced by libc when `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is not defined (`platform.h:83-88`).
- `mbedtls_platform_set_calloc_free` is only declared in the runtime configuration. Calling it when the macros are set is a compile error.

**What the library does with the facility itself**

`mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) is Mbed TLS's own allocator. It needs `MBEDTLS_MEMORY_BUFFER_ALLOC_C` plus the platform layer. It:

- initializes a static global heap `heap` over a caller-supplied buffer,
- installs its own `buffer_alloc_calloc` and `buffer_alloc_free` through `mbedtls_platform_set_calloc_free()`. If `MBEDTLS_THREADING_C` is on, it installs the mutexed variants and initializes `heap.mutex`.

So a project that wants a fixed-pool allocator with no libc heap can skip writing one. The trade-off is that the heap is process-global, so only one buffer heap exists at a time.

I did not open the bodies of `buffer_alloc_calloc` or `buffer_alloc_free`, so I haven't checked their fragmentation or failure behaviour.