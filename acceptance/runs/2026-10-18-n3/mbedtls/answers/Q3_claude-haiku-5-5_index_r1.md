**Short answer:** every allocation in the library goes through two function-like names, `mbedtls_calloc` and `mbedtls_free`. By default those forward to the C standard `calloc` and `free`. A project can replace them at build time with macros, or at run time with `mbedtls_platform_set_calloc_free()`. The library's own stack allocator uses the run-time hook to take over the heap.

**Call chain (default build)**

```
library code  →  mbedtls_calloc(n, sz)            (library/platform.c:47)
                   → (*mbedtls_calloc_func)(n, sz)   function pointer
                       → calloc                  (MBEDTLS_PLATFORM_STD_CALLOC, platform.h:84)

library code  →  mbedtls_free(p)                  (library/platform.c:52)
                   → (*mbedtls_free_func)(p)        → free
```

The two pointers are initialised at `library/platform.c:44-45` to `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. If the config does not define those, they fall back to `platform_calloc_uninit` and `platform_free_uninit` (`platform.c:25-42`). Those stubs return NULL and do nothing, so an allocation fails cleanly rather than crashing.

**How a project substitutes its allocator**

`include/mbedtls/platform.h:138-168` selects one of three modes:

| Mode | Config | Result |
|---|---|---|
| No platform memory hook | `MBEDTLS_PLATFORM_MEMORY` off | `mbedtls_calloc` is a macro for `calloc`; no indirection |
| Compile-time macros | `MBEDTLS_PLATFORM_MEMORY` + `MBEDTLS_PLATFORM_CALLOC_MACRO` + `MBEDTLS_PLATFORM_FREE_MACRO` | `mbedtls_calloc`/`mbedtls_free` expand straight to your names. The run-time setter is compiled out (`platform.c:20-22`). |
| Run-time hook | `MBEDTLS_PLATFORM_MEMORY`, macros not both defined | The function-pointer path above. The project calls `mbedtls_platform_set_calloc_free(my_calloc, my_free)` once, before any allocation. |

Both macros default to off (`mbedtls_config.h:4150-4151`). I did not confirm the default of `MBEDTLS_PLATFORM_MEMORY` itself.

To substitute in practice:
- **Compile-time:** define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free` in your user config. This is zero-overhead and has no global mutable state.
- **Run-time:** define only `MBEDTLS_PLATFORM_MEMORY`, then call the setter during init. Remember the setter is a plain pointer write with no locking.

**What the library does with the facility**

- **Routes everything through it.** Dossier lists dozens of callers of `mbedtls_calloc` and `mbedtls_free` across ciphers, ASN.1, X.509, SSL, PSA, and bignum. A grep of `library/` for bare `calloc`/`malloc`/`free` found no direct calls outside the allocator itself, with one exception noted below.
- **Owns its own allocator.** `mbedtls_memory_buffer_alloc_init()` (`library/memory_buffer_alloc.c:566`) zeroes its heap, then calls `mbedtls_platform_set_calloc_free()` with `buffer_alloc_calloc_mutexed`/`buffer_alloc_free_mutexed` when `MBEDTLS_THREADING_C` is set, or the unlocked variants otherwise (`memory_buffer_alloc.c:570-576`). From then on every `mbedtls_calloc` call is served from the caller-supplied buffer. This is a built-in way to run with no libc heap.

**Things to watch**

1. **Stack allocator is not undone.** The grep found `mbedtls_platform_set_calloc_free` called only from `init`. I found no reset back to `calloc`/`free` on teardown, so the global pointers keep pointing at the buffer allocator after `mbedtls_memory_buffer_alloc_free()`. I read this from grep hits and did not open that function, so treat it as likely rather than confirmed.
2. **One direct `free`.** `memory_buffer_alloc.c:404` calls `free(hdr->trace)` directly rather than `mbedtls_free`. I did not check where `hdr->trace` is allocated. If it is allocated by the library through the hook, this call would mismatch the allocator in a project that substitutes one.
3. **No thread safety for the setter.** Calling `mbedtls_platform_set_calloc_free` while other threads allocate is a data race. Set it once at startup.
4. **Compile-time macros win.** If both macros are defined, any later run-time call to the setter does not exist in the build at all, so there is no silent override.