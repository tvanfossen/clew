**Short answer:** every library allocation goes through `mbedtls_calloc()` / `mbedtls_free()`. Those are thin wrappers that call through two file-static function pointers in `library/platform.c`. The pointers are set by `mbedtls_platform_set_calloc_free()`, which a project calls to substitute its own allocator. The library also ships its own allocator, `memory_buffer_alloc`, which installs itself through that same setter.

**Call chain**

```
library code (e.g. mbedtls_md_setup, ssl_*, x509_*)
  -> mbedtls_calloc(n, size)          library/platform.c:47
       -> (*mbedtls_calloc_func)(n, size)
            default: MBEDTLS_PLATFORM_STD_CALLOC
  -> mbedtls_free(ptr)                library/platform.c:52
       -> (*mbedtls_free_func)(ptr)
            default: MBEDTLS_PLATFORM_STD_FREE
```

**What gets called by default**

- `mbedtls_calloc_func` and `mbedtls_free_func` are `static` pointers at `library/platform.c:44-45`. They are initialized from `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`.
- `MBEDTLS_PLATFORM_STD_CALLOC` expands to `calloc` when the integrator defines it (`include/mbedtls/platform.h:84`). Its shipped default state is off (`mbedtls_config.h:4124`).
- When it is not defined, `library/platform.c:24-33` falls back to a stub, `platform_calloc_uninit`, which returns `NULL`. The free side has the same pattern with `platform_free_uninit` (`platform.c:35-42`).
- My reading of the index is that a stock build therefore fails every allocation until the platform supplies an allocator. I inferred this from the macro expansions and default states, not from a test, so confirm it against the shipped config.

**How a project substitutes its allocator**

There are two routes.

1. **Function-pointer route (runtime).** Keep `MBEDTLS_PLATFORM_MEMORY` on and call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other mbedtls call. The setter (`platform.c:57-63`) just stores the two pointers and returns 0. It does no validation, and it is not thread-safe, so call it during init.
2. **Macro route (compile time).** Define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in the user config. Then `mbedtls_calloc` and `mbedtls_free` expand straight to the project's functions (`platform.h:139-145`) and the pointer indirection is compiled out. The test config `tests/configs/user-config-malloc-0-null.h` is an example of this style. In this route the setter and pointers are not part of the build; that is an inference from the gating, not something I read directly.

For the macro route, the index has no definition site for `MBEDTLS_PLATFORM_CALLOC_MACRO` (it is a project-supplied symbol), so the project's own header must provide it.

**What the library does with the facility**

- **Substitution is global.** The pointers are file-static and process-wide, so one allocator serves all contexts.
- **Built-in allocator, `memory_buffer_alloc`.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566-600`) zeroes the caller's buffer, sets up a first-fit free list with magic-number headers, and then calls `mbedtls_platform_set_calloc_free`. It installs `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed` when `MBEDTLS_THREADING_C` is on, and the unlocked `buffer_alloc_calloc` / `buffer_alloc_free` otherwise. The allocator then never calls the system `calloc`/`free`. It returns `NULL` on overflow and rejects `n * size` overflow explicitly. It also exits on corrupted free-list blocks.
- **Allocation sites.** Context constructors (`aes_ctx_alloc`, `gcm_ctx_alloc`, `rsa_alloc_wrap`, `mbedtls_md_setup`, …), ASN.1/X.509/PK parsers, SSL session and handshake code, and PSA key slots all go through `mbedtls_calloc`. The matching frees use `mbedtls_free`. `mbedtls_zeroize_and_free` also frees through `mbedtls_free`.

**Gaps in what I could verify**

The index does not record the repository's own default configuration, so the shipped defaults above come from the default-state annotations rather than the active config. Where I describe the macro route's compile-time gating, I am inferring it from `#if` ranges rather than reading the preprocessor branches.