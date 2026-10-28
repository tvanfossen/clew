**Short answer:** library code never calls `calloc`/`free` directly. It calls `mbedtls_calloc` and `mbedtls_free`, and what those reach depends on one build switch, `MBEDTLS_PLATFORM_MEMORY`. Substitution is either compile-time (macros) or run-time (function pointers).

**What a call resolves to**

With `MBEDTLS_PLATFORM_MEMORY` off (the default in `mbedtls_config.h:208`), `include/mbedtls/platform.h:167` makes `mbedtls_calloc` expand straight to `calloc`, and `:166` does the same for `mbedtls_free`. Nothing is indirected.

With it on, `platform.h:144` expands `mbedtls_calloc` to `MBEDTLS_PLATFORM_CALLOC_MACRO`, and `:143` does the same for free. The real function is then:

```
library code
  → mbedtls_calloc()            library/platform.c:47
    → (*mbedtls_calloc_func)()  static pointer, platform.c:44
      → default: MBEDTLS_PLATFORM_STD_CALLOC
                 (platform.c:24-33; if that is undefined, platform_calloc_uninit returns NULL)
```

`mbedtls_free` at `platform.c:52` calls `mbedtls_free_func` the same way.

**How a project substitutes its allocator**

1. **Compile-time.** Enable `MBEDTLS_PLATFORM_MEMORY` and define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` (for example `my_calloc`, `my_free`) in the user config. The library then calls those names directly, with no pointer hop. The repo's own test config does this with `MBEDTLS_PLATFORM_STD_CALLOC` set to `custom_calloc` (`tests/configs/user-config-malloc-0-null.h:20-21`).
2. **Run-time.** Enable `MBEDTLS_PLATFORM_MEMORY`, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (`platform.c:57-63`). It just overwrites the two static pointers. This is the only route that can be changed after startup.

The index does not show user-side callers of `mbedtls_platform_set_calloc_free` (it is a public API, so the only internal caller is the built-in allocator below). I did not check the `#if` polarity of `platform_calloc_uninit` against the source; the "returns NULL" behaviour is what the function body says, but when it is selected is inferred from its gate.

**What the library does with the facility**

- **Everything allocates through the wrappers.** The index shows `mbedtls_calloc` called from the cipher wrappers (`cipher_wrap.c`), ECP and bignum (`mbedtls_mpi_grow`), PK, PEM, PKCS#7, X.509, the SSL/TLS code and PSA. Frees go through `mbedtls_free`, including `mbedtls_zeroize_and_free` (`platform_util.c`), which wipes before freeing.
- **Built-in heap allocator.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566`) carves allocations out of a caller-supplied buffer. It calls `mbedtls_platform_set_calloc_free` to point the hooks at its own functions. With `MBEDTLS_THREADING_C`, those are mutex-wrapped variants (`buffer_alloc_calloc_mutexed` / `buffer_alloc_free_mutexed`, lines 541-563). The free variant returns without freeing if the lock fails, on the stated reasoning that losing memory is safer than corrupting the heap.
- **Caveat: it is process-global.** `memory_buffer_alloc_init` replaces the hooks for every context in the process, not one context.
- **Caveat: vendored code.** `3rdparty/everest/.../kremlin/internal/target.h` defines its own `KRML_HOST_CALLOC`. I did not confirm whether that expands to `mbedtls_calloc`, so treat it as bypassing the hooks until checked.

**Index caveats:** this index was built with `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` passed as flags, and no config header is recorded for the target. The "off by default" state of `MBEDTLS_PLATFORM_MEMORY` comes from a heuristic on `mbedtls_config.h`, so confirm it against the shipped header.