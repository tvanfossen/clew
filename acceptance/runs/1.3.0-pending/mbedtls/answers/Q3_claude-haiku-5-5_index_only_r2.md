**Short answer:** every allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`. Those two functions call through file-static function pointers, which default to libc `calloc`/`free` and can be replaced at runtime. A project can also bypass the pointers at compile time by pointing the macros at its own functions.

**What gets called**

```
library code  →  mbedtls_calloc(n, size)            library/platform.c:47
                   └─ (*mbedtls_calloc_func)(n, size)
                        mbedtls_calloc_func = MBEDTLS_PLATFORM_STD_CALLOC   (platform.c:44)
                        → calloc                                             (platform.h:84)

library code  →  mbedtls_free(ptr)                  library/platform.c:52
                   └─ (*mbedtls_free_func)(ptr)
```

- Callers include the cipher, PK, ECP, bignum, ASN.1, X.509, SSL and PSA modules. The index shows `mbedtls_calloc` with about 90 callers and `mbedtls_free` with about 100, and I saw no direct `calloc` in the library call paths it returned. `mbedtls_zeroize_and_free` also goes through `mbedtls_free`.
- The default-state column in the index marks `MBEDTLS_PLATFORM_MEMORY` as off in the shipped config (`mbedtls_config.h:208`). The `MBEDTLS_PLATFORM_STD_CALLOC` default is a heuristic, not a verified read. I did not confirm the free-side default initializer.

**How a project substitutes its allocator**

Two mechanisms, both gated on `MBEDTLS_PLATFORM_MEMORY`:

1. **Runtime, function pointers.** Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (`library/platform.c:57`). It has signature `void *(*)(size_t, size_t)` and `void (*)(void *)`, returns 0, and only assigns the two globals. It takes no lock, so install the allocator before any threads start.
2. **Compile time, macros.** Define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` (`include/mbedtls/platform.h:138-145`). `mbedtls_calloc` and `mbedtls_free` then expand straight to the project's functions and the pointer dispatch is skipped. The index has no definition site for these two macros, which is expected because they are user-supplied. The test config `tests/configs/user-config-malloc-0-null.h` shows the pattern with `custom_calloc`.

The index gates the setter and the pointer block (`platform.c:20-64`) on `MBEDTLS_PLATFORM_MEMORY`, with the two macros also named in that gate. So the runtime setter appears to exist only when `MBEDTLS_PLATFORM_MEMORY` is defined and the macro overrides are not. I inferred the exact `#if` expression from the gate list and did not read it.

`MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` removes the standard-library names (`platform.h:57`). The index also has a `platform_calloc_uninit` stub that returns NULL, which is what the standard-calloc slot points at in a configuration with no libc calloc. A test component, `component_test_psa_crypto_without_heap`, builds a configuration where the core library cannot use `calloc`/`free` while the test code still can.

**What the library does with the facility itself**

- It never allocates on its own. It only dispatches through `mbedtls_calloc`/`mbedtls_free`.
- It ships one substitute, a buffer-based allocator. `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566`) zeroes the heap context and calls `mbedtls_platform_set_calloc_free` to install its own functions. It installs the mutex-wrapped `buffer_alloc_calloc_mutexed`/`buffer_alloc_free_mutexed` when `MBEDTLS_THREADING_C` is on, and the unwrapped pair otherwise. It then carves the caller's buffer into aligned, magic-tagged headers.
- `mbedtls_memory_buffer_alloc_init` is the only in-library caller of the setter that the index shows. Application code (for example `programs/test/selftest.c`) calls the init function.
- `mbedtls_platform_setup` / `mbedtls_platform_teardown` are no-ops that return 0, gated on `MBEDTLS_PLATFORM_SETUP_TEARDOWN_ALT`. They do not touch the allocator.

**Caveats**

- If `mbedtls_memory_buffer_alloc_init` is used, the buffer must outlive every allocation, and it must be installed before any allocation happens. The index does not show a teardown that restores libc.
- I did not verify the exact preprocessor conditions for the `platform.h` macro block, or the free-side default. The line numbers above come from the index, not from reading the source.