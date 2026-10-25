The allocation path is two layers of indirection, and the substitution point is a set of function pointers in `library/platform.c`. Everything below comes from the index; I did not read source files directly.

**What a call does**

1. Library code calls `mbedtls_calloc(n, size)` or `mbedtls_free(p)`. These are never plain `calloc`/`free` in the normal configuration.
2. `mbedtls_calloc` and `mbedtls_free` are functions in `library/platform.c` (lines 47–55). Each just forwards through a static function pointer: `(*mbedtls_calloc_func)(nmemb, size)` and `(*mbedtls_free_func)(ptr)`.
3. Those pointers are `static` globals in `library/platform.c` (lines 44–45). They start out as `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`, which `include/mbedtls/platform.h` defines as `calloc` and `free` (line 84) unless `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set.

```
library code → mbedtls_calloc()  (platform.c:47)
             → *mbedtls_calloc_func  (static ptr, platform.c:44)
             → calloc (default) | project allocator
```

The macro layer in `include/mbedtls/platform.h` sits in front of this. When `MBEDTLS_PLATFORM_MEMORY` is defined, `mbedtls_calloc` and `mbedtls_free` are macros that expand to `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` (lines 139–145, with the function-name macros at 167 and 166 in the other branch). Without `MBEDTLS_PLATFORM_MEMORY`, the names expand straight to `calloc` and `free`. The index has no definition site for `MBEDTLS_PLATFORM_CALLOC_MACRO` or `MBEDTLS_PLATFORM_FREE_MACRO`, which is normal when a project supplies them itself.

**How a project substitutes its own allocator**

Two pieces are needed:

- Compile-time: enable `MBEDTLS_PLATFORM_MEMORY` and define the macros to name your allocator. The index's test config `tests/configs/user-config-malloc-0-null.h` does this: `MBEDTLS_PLATFORM_MEMORY` at line 20 and `MBEDTLS_PLATFORM_STD_CALLOC` set to `custom_calloc` at line 21. The `MBEDTLS_PLATFORM_CALLOC_MACRO`/`FREE_MACRO` names are the other hooks.
- Run-time: call `mbedtls_platform_set_calloc_free(calloc_func, free_func)` (`library/platform.c:57`). It assigns the two static pointers and returns 0. The function is gated on `MBEDTLS_PLATFORM_MEMORY` and `MBEDTLS_PLATFORM_C`.

Two things the body shows that matter for a substitution:

- It does no NULL check on its arguments. Passing NULL is accepted and fails later when the library calls through the pointer.
- It returns 0 unconditionally, so it can't report failure.

**What the library does with the facility**

- Most context and object allocation goes through `mbedtls_calloc`/`mbedtls_free`. The index lists over 100 callers of `mbedtls_calloc`, including cipher context setup (AES, ARIA, GCM, CCM, ChaCha20), MPI growth and modular arithmetic, PK/RSA/ECDSA key handling, X.509 and PKCS#7 parsing, SSL session and cache code, and PSA key slots. The `ctx_free` counterparts call `mbedtls_free`.
- `mbedtls_zeroize_and_free` (`library/platform_util.c:139`) zeroizes a buffer with `mbedtls_platform_zeroize` and then calls `mbedtls_free`. The index marks it orphan, with 73 unresolved callers, so I can't say how widely it's used.
- The library ships its own allocator, `mbedtls_memory_buffer_alloc_init` (`library/memory_buffer_alloc.c:566`). It carves allocations out of a caller-supplied buffer and installs itself by calling `mbedtls_platform_set_calloc_free`. With `MBEDTLS_THREADING_C` it installs mutex-wrapped variants (`buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed`). It does not call the system `calloc` or `free`.

The consequence is that the buffer allocator and a project's `mbedtls_platform_set_calloc_free` overwrite the same globals. Whichever runs last wins. That's inferred from the code, not checked by a test.

**Gaps in what the index can tell me**

- The index has no `config_header` for this target, so I can't confirm whether `MBEDTLS_PLATFORM_MEMORY` is enabled in the shipped `mbedtls_config.h`. The index only shows it defined in the TF-M profile and the malloc test config. Treat the default as unknown.
- The `#if` expression text around the `platform.c` gates is summarised, not quoted, so the exact branch conditions should be read from the source before relying on them.
- I checked callers through the index only, so I have not confirmed that no library code calls `calloc` or `free` directly.