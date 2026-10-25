**Short answer:** an mbedtls allocation is a call to `mbedtls_calloc()` (or the `mbedtls_calloc` macro), which normally dispatches through a process-wide function pointer. The default pointer is the C library's `calloc`. A project can replace it either at compile time with macros or at run time with `mbedtls_platform_set_calloc_free()`.

**What gets called, by configuration**

```
library code: mbedtls_calloc(n, sz)
        │
        ├─ MBEDTLS_PLATFORM_MEMORY off (default)
        │     └─ macro → calloc directly                 (platform.h ~167)
        │
        ├─ MBEDTLS_PLATFORM_MEMORY on, plus CALLOC/FREE_MACRO
        │     └─ macro → user's MBEDTLS_PLATFORM_CALLOC_MACRO (platform.h:139-144)
        │
        └─ MBEDTLS_PLATFORM_MEMORY on, no macros
              └─ mbedtls_calloc() in platform.c:47
                    └─ (*mbedtls_calloc_func)(n, sz)
```

- `mbedtls_calloc()` (`library/platform.c:47`) and `mbedtls_free()` (`platform.c:52`) are one-line trampolines through the static pointers `mbedtls_calloc_func` and `mbedtls_free_func` (`platform.c:44-45`).
- Those pointers are initialised to `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. `platform.h:84` defines the standard one as `calloc`. The index does not show the `MBEDTLS_PLATFORM_STD_FREE` definition, so I can't confirm the free side from it.
- If `MBEDTLS_PLATFORM_STD_CALLOC` is undefined, the fallback is `platform_calloc_uninit` (`platform.c:25-30`), which always returns NULL. So a build with `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` and no substitute fails every allocation until a function is installed.

**How a project substitutes its allocator**

1. **Compile-time, function-level (`MBEDTLS_PLATFORM_MEMORY` plus macros).** Enable `MBEDTLS_PLATFORM_MEMORY`, then define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` to your own symbols. The index has an example in `tests/configs/user-config-malloc-0-null.h`, which defines a `custom_calloc`. This binds at compile time with no pointer indirection. `mbedtls_platform_set_calloc_free` is not the mechanism in this mode.
2. **Run-time, function-pointer.** Enable `MBEDTLS_PLATFORM_MEMORY` without the macros and call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (`platform.c:57-63`) before the library allocates. It assigns the two static pointers and returns 0. It does no NULL check, so passing NULL fails later, not at the call.

Either way, the library's allocation path (`mbedtls_calloc`/`mbedtls_free`) is the single seam.

**What the library does with the facility**

- Almost every context constructor and destructor goes through the seam. Examples include `aes_ctx_alloc`/`aes_ctx_free`, `gcm_ctx_alloc`, `rsa_alloc_wrap`, `ssl_setup`/`mbedtls_ssl_free`, `x509_crt_parse_der_internal`, the PSA key-slot and buffer helpers, and the PKCS#7 and PEM code.
- `mbedtls_zeroize_and_free()` (`library/platform_util.c:139-146`) zeroes the buffer with `mbedtls_platform_zeroize` and then calls `mbedtls_free`. Secret-holding objects use it to clear memory before release.
- The library ships its own allocator, `mbedtls_memory_buffer_alloc_init()` (`library/memory_buffer_alloc.c:566-600`). You give it a static buffer, and it manages that buffer without calling `calloc`/`free`. It works by calling `mbedtls_platform_set_calloc_free` to install its own functions. With `MBEDTLS_THREADING_C` it installs mutex-wrapped variants (`buffer_alloc_calloc_mutexed`, `:541`) that lock a heap mutex around each call.

**Caveats**

- Installing an allocator is process-wide. It replaces the globals for everything in the process, not one context. That includes `mbedtls_memory_buffer_alloc_init`, which has the same global effect. The index does not show whether the setter is synchronised, so I'd install before any threads start.
- I did not dossier the `platform.h` lines 145-161 gate or the exact `#else` branch in `platform.c`. The description above follows the line ranges the index reports, not a read of the preprocessor logic.