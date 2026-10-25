**Short answer:** every library allocation goes through `mbedtls_calloc()` and `mbedtls_free()`. By default those forward to libc `calloc`/`free` through two file-static function pointers. A project can replace the allocator at build time with macros or at run time with `mbedtls_platform_set_calloc_free()`. The library's only internal use of that run-time hook is its own stack-based allocator, which installs itself as the global allocator.

**1. What gets called by default**

```
mbedtls_calloc(n, size)         library/platform.c:47
  └─ (*mbedtls_calloc_func)     platform.c:44, initialised to MBEDTLS_PLATFORM_STD_CALLOC
       └─ calloc                platform.h:84

mbedtls_free(ptr)               library/platform.c:52
  └─ (*mbedtls_free_func)       platform.c:45, initialised to MBEDTLS_PLATFORM_STD_FREE
       └─ free
```

Callers in the library use the `mbedtls_calloc`/`mbedtls_free` names, not `calloc`/`free`. The index shows them used across cipher context allocation, ASN.1, MPI growth, PK, PSA, SSL and X.509.

**2. Substitution at build time (macros)**

- `platform.h:139-145` maps `mbedtls_calloc` to `MBEDTLS_PLATFORM_CALLOC_MACRO` (line 144) and `mbedtls_free` to `MBEDTLS_PLATFORM_FREE_MACRO` (line 143). Both sit behind `MBEDTLS_PLATFORM_MEMORY`.
- A project defines those two macros in its user config. The index has the gate structure but no definition site for either macro, and no config header is recorded for this target. So I cannot confirm the shipped default or the exact polarity of the `#if`.
- The test fixture `tests/configs/user-config-malloc-0-null.h` defines a `custom_calloc` function and wires it in through `MBEDTLS_PLATFORM_STD_CALLOC`. That is a working example of the pattern, but I did not read its body.

**3. Substitution at run time (function pointers)**

`mbedtls_platform_set_calloc_free(calloc_func, free_func)` (`platform.c:57-63`) assigns the two statics and returns 0. The body has no NULL check, no lock and no return-value check. A project calls it before any allocation, with its own `calloc`- and `free`-shaped functions.

**4. What the library does with the facility**

`mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566-600`) is the library's own user of the hook:

- It zeroes its heap context, then calls `mbedtls_platform_set_calloc_free`. It passes the mutexed variants when `MBEDTLS_THREADING_C` is defined, and the plain variants otherwise.
- It only then checks `len` and aligns the buffer. From the body, a too-small buffer returns early but leaves the buffer allocator installed globally. With `heap.buf == NULL`, `buffer_alloc_calloc` (`:199-278`) returns NULL for every request. This is my reading of the code, not something the index states as a finding, so treat it as worth verifying.
- The function is process-wide. Installing it changes allocation for every Mbed TLS object in the process.

**Gaps in the index**

- Default value of `MBEDTLS_PLATFORM_CALLOC_MACRO` / `FREE_MACRO`: no definition site and no `config_header`, so unknown.
- Whether `mbedtls_platform_set_calloc_free` is safe to call while other threads allocate: the body shows no synchronisation, but I did not query locks.
- The `#if` polarity of the `platform.c:20-64` block and the `platform.h` branches: the index gives gate expressions without their conditions, so the two modes above come from the gate structure, not a read of the condition.