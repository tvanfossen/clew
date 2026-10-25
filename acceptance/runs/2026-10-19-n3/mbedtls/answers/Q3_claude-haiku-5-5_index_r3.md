Short answer: every allocation in the library goes through two indirection points, `mbedtls_calloc()` and `mbedtls_free()`. Those forward to function pointers that default to the C standard allocator, and a project replaces them either at build time with two macros or at run time with `mbedtls_platform_set_calloc_free()`. The library's own stack-based allocator is one of the things that uses that hook.

**1. What the library calls**

Library code calls `mbedtls_calloc(n, size)` and `mbedtls_free(ptr)`, never `calloc`/`free` directly. Examples: the context constructors and destructors (`aes_ctx_alloc`, `gcm_ctx_free`, and so on), the X.509 and PK parsers, and the SSL session code. The one bare `free()` I found in `library/` is in `memory_buffer_alloc.c:404`, inside the `MBEDTLS_MEMORY_BACKTRACE` debug path, which frees a trace buffer. Nothing else calls the stdlib directly.

**2. How the indirection is wired** (`library/platform.c`, `include/mbedtls/platform.h`)

- `platform.c:44-45` declares two static function pointers, `mbedtls_calloc_func` and `mbedtls_free_func`, initialised to `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`.
- `platform.c:47-55` defines `mbedtls_calloc` and `mbedtls_free` as thin wrappers that dereference those pointers.
- `platform.c:57-63` defines `mbedtls_platform_set_calloc_free()`, which just overwrites the two pointers.
- If `MBEDTLS_PLATFORM_STD_CALLOC` / `_FREE` are not defined, the defaults are no-op stubs: calloc returns NULL and free does nothing. Mbed TLS does not silently fall back to libc in that case.

**3. The three substitution modes**

| Config | `mbedtls_calloc` resolves to | Resolved when |
|---|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (default) | `calloc` / `free` from libc (`platform.h:166-167`) | Preprocessor |
| `MBEDTLS_PLATFORM_MEMORY` + both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | your macro names (`platform.h:143-144`) | Compile time, zero runtime cost |
| `MBEDTLS_PLATFORM_MEMORY` alone (or with only one macro) | the wrapper functions above, pointing to whatever was set | Run time, via `mbedtls_platform_set_calloc_free()` |

The two macros must be defined together, and if both are present the runtime setter is compiled out (`platform.c:20-22`, `platform.h:139`). `mbedtls_config.h:155-207` documents this precedence.

**How a project uses it**

- Compile-time: in its user config header, define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free`, and point the build at that header. Those macros must match the `calloc`/`free` signatures.
- Run-time: define only `MBEDTLS_PLATFORM_MEMORY` (and `MBEDTLS_PLATFORM_C`, which it depends on). Then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other library call. Any allocation made before the call hits the stub and fails with NULL.

**4. What the library does with the facility itself**

`library/memory_buffer_alloc.c:566-576` (`mbedtls_memory_buffer_alloc_init`) is the built-in heap. It is an allocator that carves allocations out of a caller-supplied buffer, and it uses the same hook to install itself. On init, it calls `mbedtls_platform_set_calloc_free(buffer_alloc_calloc_mutexed, buffer_alloc_free_mutexed)` (or the unmutexed pair without `MBEDTLS_THREADING_C`). From then on, every `mbedtls_calloc` / `mbedtls_free` in the library is served from that buffer. The header comment says it "does not call calloc() and free()". Its self-tests at `memory_buffer_alloc.c:658`, `687` and `715` exercise this path.

Caveats:
- That init replaces the global hook process-wide, so it is not a per-context allocator.
- With `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` defined, the setter is compiled out, so `mbedtls_memory_buffer_alloc_init` cannot take effect. Since it calls `mbedtls_platform_set_calloc_free`, it would be a link error in that build; I did not confirm that build outcome, so treat that as an inference.
- Thread-safety of the custom allocator is the project's responsibility unless `MBEDTLS_THREADING_C` is enabled.

I did not build or run anything; this is from reading the source and the index.