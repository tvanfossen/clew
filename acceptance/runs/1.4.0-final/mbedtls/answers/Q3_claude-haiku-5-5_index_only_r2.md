**Short answer:** library code never calls `calloc`/`free` directly. It calls `mbedtls_calloc`/`mbedtls_free`, and what those resolve to depends on two config switches. The default build calls libc. With `MBEDTLS_PLATFORM_MEMORY` on, they dispatch through function pointers that a project can replace at runtime. I read this from the index's symbol and gate data, not from the full source, so the conditional details are worth confirming in `include/mbedtls/platform.h` and `library/platform.c`.

**What gets called, by configuration**

| Config | `mbedtls_calloc` / `mbedtls_free` resolve to |
|---|---|
| Default (`MBEDTLS_PLATFORM_MEMORY` off) | Macros to libc `calloc` / `free` (`platform.h:167`, `:166`). No indirection. |
| `MBEDTLS_PLATFORM_MEMORY` on, no custom macros | Real functions in `platform.c:47` and `:52`. Each calls through a static pointer, `mbedtls_calloc_func` / `mbedtls_free_func` (`platform.c:44`). |
| `MBEDTLS_PLATFORM_CALLOC_MACRO` / `FREE_MACRO` defined | Macros expanding to the project's own names (`platform.h:143`, `:144`). |

The static pointer defaults to `MBEDTLS_PLATFORM_STD_CALLOC`. That macro is off in the shipped config (`mbedtls_config.h:4124`). If it is undefined, `platform.c:32` falls back to `platform_calloc_uninit`, which always returns NULL. So a memory-hook build that never installs an allocator fails every allocation. This is inferred from the gate data, so verify it before relying on it.

**How a project substitutes its allocator**

Two routes, both shown in the index:

1. **Compile-time macros.** Enable `MBEDTLS_PLATFORM_MEMORY` and define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in the user config. Those names then replace calloc/free everywhere. The shipped headers do not define these macros, so the project must supply them.
2. **Runtime hooks.** Enable `MBEDTLS_PLATFORM_MEMORY` and call `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)` (`platform.c:57`). It just stores the two pointers. The repository's own test config, `tests/configs/user-config-malloc-0-null.h`, does this via `MBEDTLS_PLATFORM_STD_CALLOC` = `custom_calloc`.

**What the library does with the facility**

- **Everything routes through the wrapper.** Callers include the cipher context allocators in `cipher_wrap.c`, the MD context macro `ALLOC` in `md.c`, `pk_wrap.c`, `ecp.c`, `pem.c`, `pkcs7.c`, `asn1parse.c`, and the SSL free paths in `ssl_tls.c`. The `ALLOC` macro in `md.c` maps a NULL return to `MBEDTLS_ERR_MD_ALLOC_FAILED`.
- **It ships its own allocator.** `mbedtls_memory_buffer_alloc_init` (`memory_buffer_alloc.c:566`) takes a caller-supplied buffer and carves it into blocks with headers. It installs its own calloc/free through `mbedtls_platform_set_calloc_free`. With `MBEDTLS_THREADING_C` it uses mutex-wrapped variants. This makes a fixed-heap, no-libc-heap configuration possible.
- **Its failure modes differ.** On exhaustion, `buffer_alloc_calloc` returns NULL. On corruption, double free, or a pointer outside the managed buffer, `buffer_alloc_free` calls `mbedtls_exit(1)` rather than returning an error. The allocator also has verify, status, max-usage and self-test helpers, and an optional backtrace.

Caveat: the index shows that `mbedtls_memory_buffer_alloc_init` installs these hooks through the same `set_calloc_free` path a project would use. It does not show whether the library itself checks which allocator is active.