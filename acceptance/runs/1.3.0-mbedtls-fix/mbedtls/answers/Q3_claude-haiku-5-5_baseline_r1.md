**Short answer:** every allocation inside the library goes through `mbedtls_calloc()` and `mbedtls_free()`. What those names resolve to depends on the build configuration. By default they are plain libc `calloc`/`free`. With `MBEDTLS_PLATFORM_MEMORY` they become indirections through function pointers that the embedder can replace, either at compile time or at runtime.

**What gets called**

- **No `MBEDTLS_PLATFORM_MEMORY` (default):** `include/mbedtls/platform.h:163-168` makes `mbedtls_calloc` a macro for `calloc` and `mbedtls_free` a macro for `free`. There is no indirection.
- **`MBEDTLS_PLATFORM_MEMORY` plus both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`:** `platform.h:143-144` maps the names straight to those macros at compile time. `library/platform.c` compiles out entirely in this case.
- **`MBEDTLS_PLATFORM_MEMORY` alone:** `platform.h:148-149` declares real functions `mbedtls_calloc()` and `mbedtls_free()`. `library/platform.c:44-63` implements them as calls through two static function pointers. Those pointers start at `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`, which default to libc `calloc`/`free` when the `STD` names are not overridden. If the embedder defines `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` without providing those names, the defaults are stubs: calloc returns NULL and free does nothing (`platform.c:25-42`). Per `mbedtls_config.h:4113-4134`, an uninitialised calloc always fails.

**How a project substitutes its own allocator**

1. Enable `MBEDTLS_PLATFORM_MEMORY` in its `mbedtls_config.h` (or via `-D`). `MBEDTLS_PLATFORM_C` is required.
2. Pick one of two routes:
   - **Compile time:** define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` to your functions. Both must be set together (`check_config.h:558-573` enforces this). Your names must be visible to every translation unit, so they usually go in a header included from the config.
   - **Run time:** leave the macros undefined and call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other Mbed TLS call. Alternatively, set `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` to your functions at build time, which is the same mechanism with a different default.
3. Your `calloc` must return NULL on failure and zero the memory. Your `free` must accept NULL. Mbed TLS checks every allocation for NULL. `mbedtls_free` is called on pointers that came from `mbedtls_calloc`, so the two must be paired.

**What the library does with the facility**

- The library never calls libc `calloc`/`malloc`/`free` directly. A grep of `library/` finds only comments and one `free(hdr->trace)` in `memory_buffer_alloc.c:404`, which belongs to the debugging trace code. Every other allocation goes through `mbedtls_calloc`/`mbedtls_free`, and there are roughly 350 such call sites in about 50 files, including `ssl_tls.c`, `x509*.c`, `psa_crypto*.c`, and the `pk_wrap.c` and `cipher_wrap.c` backends.
- `mbedtls_zeroize_and_free()` (`library/platform_util.c:139-145`) wipes a buffer and then calls `mbedtls_free`, so secrets are cleared before the allocator sees them.
- The library ships its own allocator, `library/memory_buffer_alloc.c`, enabled by `MBEDTLS_MEMORY_BUFFER_ALLOC_C`. Calling `mbedtls_memory_buffer_alloc_init(buf, len)` installs it by calling `mbedtls_platform_set_calloc_free()` internally (`memory_buffer_alloc.c:566-576`). It carves allocations out of a caller-supplied static buffer, with a mutex if `MBEDTLS_THREADING_C` is on. Its free path reports a fatal error for pointers outside its heap.

**Caveats**

- `mbedtls_platform_set_calloc_free()` changes process-wide global state, not per-context state. Call it once, before any threads start, and do not switch allocators while objects allocated by the old one are still live.
- Runtime substitution is only as good as the call order. Any allocation made before the setter runs goes through the default, and freeing it later through the new allocator is undefined behaviour.
- The `MBEDTLS_MEMORY_BUFFER_ALLOC_C` path also depends on the caller's buffer being alive for the life of the library use.

I did not build or run anything. The conclusions come from reading `platform.c`, `platform.h`, `mbedtls_config.h`, `memory_buffer_alloc.c` and the call-site grep.