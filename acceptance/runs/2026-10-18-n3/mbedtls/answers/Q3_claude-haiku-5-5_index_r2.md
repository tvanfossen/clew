**Short answer:** every allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`. Those are thin wrappers that call a pair of function pointers. By default the pointers point at libc `calloc`/`free`, and a project can repoint them at runtime or at compile time. The library never calls `malloc` or `free` directly, with one debug-only exception.

**What gets called**

1. Library code calls `mbedtls_calloc(n, size)` or `mbedtls_free(p)`. These are declared in `include/mbedtls/platform.h:148-149`.
2. In the default runtime configuration, those are real functions in `library/platform.c:47-55`. Each one dereferences a file-static pointer, `mbedtls_calloc_func` or `mbedtls_free_func` (`platform.c:44-45`), and calls it.
3. The pointers start at `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. If the project does not define them, they fall back to `platform_calloc_uninit` (always returns NULL) and `platform_free_uninit` (no-op), per `platform.c:24-42`. So an unconfigured build fails allocations cleanly rather than crashing.
4. Some callers use `mbedtls_zeroize_and_free()` (`library/platform_util.c:139-146`), which zeroizes the buffer and then calls `mbedtls_free`.

**How a project substitutes its allocator**

There are two mechanisms, and the compile-time one wins if both are set (`platform.c:16-19`).

- **Compile-time macros.** Define `MBEDTLS_PLATFORM_MEMORY`, then define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` (they must be set together). `platform.h:139-144` then `#define`s `mbedtls_calloc` and `mbedtls_free` straight to the macros. No function-pointer indirection and no `platform.c` code is involved.
- **Runtime hook.** Define `MBEDTLS_PLATFORM_MEMORY` and leave the macros undefined. Then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (`platform.c:57-63`) before any allocation. You can optionally override `MBEDTLS_PLATFORM_STD_CALLOC` / `STD_FREE` in your config to set the initial values. Without `MBEDTLS_PLATFORM_MEMORY`, the header maps `mbedtls_calloc` to plain libc `calloc` (`platform.h:163-168`).

The config documentation for all of this is in `include/mbedtls/mbedtls_config.h:155-201` and `4113-4151`.

**What the library does with the facility**

- It never calls the allocator directly. Context constructors such as `aes_ctx_alloc`, `gcm_ctx_alloc`, and the ECP/ASN.1/X.509 code all go through `mbedtls_calloc`, and their matching `*_free` functions go through `mbedtls_free`. The same is true of most of the TLS, PSA and PK paths. These are the call sites the index lists as callers of `mbedtls_calloc`.
- `mbedtls_memory_buffer_alloc_init()` (`library/memory_buffer_alloc.c:566-600`) is a built-in allocator. It carves allocations out of a caller-supplied buffer, with no libc involved. It works by calling `mbedtls_platform_set_calloc_free()` with its own `buffer_alloc_calloc` / `buffer_alloc_free` functions. It uses the mutexed variants when `MBEDTLS_THREADING_C` is on. So it is the same substitution hook, used by the library itself.
- **Exception:** with `MBEDTLS_MEMORY_BACKTRACE` enabled, the buffer allocator stores `backtrace_symbols()` output in each block (`memory_buffer_alloc.c:281-282`, `347-348`) and releases it with libc `free()` (`memory_buffer_alloc.c:404`). That memory bypasses the substitutable path. It is a debugging feature, and the bypass only matters if you are relying on the custom allocator for every byte.

**Caveat for substitution:** the pointers are global, so set them once before any allocation and do not change them mid-session. The buffer allocator does the same, and it states that the function pointers must be thread-safe when threading is enabled.