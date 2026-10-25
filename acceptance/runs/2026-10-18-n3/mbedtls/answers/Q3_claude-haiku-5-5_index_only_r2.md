**Short answer:** With the default build, `mbedtls_calloc()` and `mbedtls_free()` are thin wrappers that call through two global function pointers, `mbedtls_calloc_func` and `mbedtls_free_func`. Those pointers default to the C library's `calloc` and `free`. A project can replace them at compile time or at runtime. The library's own stack-based allocator is one client of the runtime hook.

**What a call resolves to**

The index shows two build-time paths in `include/mbedtls/platform.h`:

- **`MBEDTLS_PLATFORM_MEMORY` not defined:** library code calls `calloc` and `free` directly. The `mbedtls_calloc` and `mbedtls_free` names expand to those (lines 163–168).
- **`MBEDTLS_PLATFORM_MEMORY` defined:** `mbedtls_calloc` and `mbedtls_free` are indirected (lines 138–163):
  - If `MBEDTLS_PLATFORM_CALLOC_MACRO` or `MBEDTLS_PLATFORM_FREE_MACRO` is defined, the name becomes that macro. This is a compile-time substitution with no runtime pointer.
  - Otherwise, `library/platform.c` provides the functions `mbedtls_calloc` (lines 47–50) and `mbedtls_free` (lines 52–55). Each one just forwards to `(*mbedtls_calloc_func)(nmemb, size)` or `(*mbedtls_free_func)(ptr)`.

Most of the library never names `calloc` or `malloc` itself. Its allocations go through `mbedtls_calloc`, for example in cipher context allocation, MPI growth, SSL setup, and X.509 parsing. Frees go through `mbedtls_free`, including `mbedtls_zeroize_and_free`. The index also has a `MBEDTLS_PLATFORM_STD_CALLOC` symbol, which I expect is the default for the function pointers, but I did not read the initializer for `mbedtls_calloc_func` and cannot confirm it from the index.

**How a project substitutes its allocator**

Two options:

1. **Compile time.** Enable `MBEDTLS_PLATFORM_MEMORY` and define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` to the project's names. The repo's `tests/configs/user-config-malloc-0-null.h` and `configs/ext/tfm_mbedcrypto_config_profile_medium.h` both define `MBEDTLS_PLATFORM_MEMORY`, so that is the pattern to follow. The index has no definition site for the two `_MACRO` symbols in the shipped headers, so check `mbedtls_config.h` for the default.
2. **Runtime.** Enable `MBEDTLS_PLATFORM_MEMORY` and call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` once, before any other mbedtls call. The function, at `library/platform.c:57–63`, stores both pointers and returns 0. It does no NULL checks, and the index shows no thread-safety guarantee for it.

**What the library does with the facility itself**

The library also ships an allocator that uses this hook. `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566–600`):

- Zeroes a global heap context and, if `MBEDTLS_THREADING_C` is set, initializes a mutex.
- Calls `mbedtls_platform_set_calloc_free` with its own `buffer_alloc_calloc` and `buffer_alloc_free`. The mutexed variants are used when threading is enabled.
- Aligns the caller's buffer, zeroes it, and writes a first block header with magic values.

After that call, every `mbedtls_calloc` and `mbedtls_free` allocates from the caller's buffer and never touches the system heap. The caller is the application. Its `main` is the indexed caller, not the library itself. The library only provides the allocator and the hook.

**Caveats**

- The index's `configured_macros` reflects the build used to index this repo, not the repo's shipped defaults. I could not confirm the default state of `MBEDTLS_PLATFORM_MEMORY` or the `_MACRO` symbols from the index.
- I did not read the initializers of the two function pointers, so the exact default bindings are inferred from the `MBEDTLS_PLATFORM_STD_CALLOC` symbol.