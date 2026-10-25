**Short answer:** every allocation in the library goes through two names, `mbedtls_calloc` and `mbedtls_free`. What those names resolve to is decided at build time. By default they are the libc `calloc` and `free`. A project can replace them at compile time with macros, or at run time with `mbedtls_platform_set_calloc_free()`.

**What gets called**

`include/mbedtls/platform.h` picks the binding:

| Config | `mbedtls_calloc` / `mbedtls_free` resolve to |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` not defined (lines 163–167) | the macros `calloc` / `free` directly |
| `MBEDTLS_PLATFORM_MEMORY` + both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` (lines 139–144) | the user's macros, expanded at compile time |
| `MBEDTLS_PLATFORM_MEMORY` alone (lines 145–162) | real functions defined in `library/platform.c`, which dispatch through function pointers |

The pointer-based case is the one with runtime behaviour. In `library/platform.c:44–61`:

- Two static function pointers, `mbedtls_calloc_func` and `mbedtls_free_func`, start at `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE`.
- `mbedtls_calloc()` and `mbedtls_free()` just call through those pointers.
- `mbedtls_platform_set_calloc_free()` overwrites the pointers and always returns 0. It does no NULL check.
- If `MBEDTLS_PLATFORM_STD_CALLOC` is not defined, the default is a stub that returns NULL, so any allocation before setup fails. If it is defined (for example as `calloc`), that becomes the default.

**How a project substitutes its allocator**

- **Compile time:** set `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free` in its config header. The check in `check_config.h` requires both macros together and both prerequisites. This adds no indirection.
- **Run time:** set `MBEDTLS_PLATFORM_MEMORY` without the macros. At startup, call `mbedtls_platform_set_calloc_free(my_calloc, my_free)`. Either set `MBEDTLS_PLATFORM_STD_CALLOC` / `_FREE` to give a default, or make sure the call happens before the library allocates anything.

**What the library does with it**

- The library never calls `malloc`, `calloc` or `free` directly. A grep of `library/` finds only comments and strings. Roughly 176 uses of `mbedtls_calloc` / `mbedtls_free` appear across about 49 files, including `ssl_tls.c`, `psa_crypto.c`, `x509.c` and `asn1parse.c`.
- The library's own built-in heap, `library/memory_buffer_alloc.c` (`MBEDTLS_MEMORY_BUFFER_ALLOC_C`), is an allocator plugged into this facility. `mbedtls_memory_buffer_alloc_init(buf, len)` installs it by calling `mbedtls_platform_set_calloc_free(buffer_alloc_calloc, buffer_alloc_free)` (lines 572–575). Lines 572–573 register a mutex-wrapped variant instead. I did not trace the condition that selects it. The test and sample programs use this heap with a static buffer.

**Caveats**

- The library does not record which allocator produced a pointer. If you swap allocators after the library has allocated, `mbedtls_free()` will send old pointers to the new `free`. Set the allocator once, before any Mbed TLS call.
- `mbedtls_platform_set_calloc_free()` has no failure path and no NULL validation, so passing NULL in either slot will crash at the first call.

I did not run a build or tests, so the compile-time and run-time behaviour above comes from reading the source.