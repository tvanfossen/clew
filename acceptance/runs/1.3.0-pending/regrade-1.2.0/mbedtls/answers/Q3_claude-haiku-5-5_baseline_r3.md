**Short answer:** library code never calls `calloc`/`free` directly. It calls `mbedtls_calloc()` and `mbedtls_free()`, and what those resolve to depends on build configuration. Either they are macros that expand to the libc functions or a project's allocator, or they are functions that dispatch through function pointers that can be swapped at runtime.

## What gets called

```
library code ──► mbedtls_calloc(n, sz) / mbedtls_free(p)
                    │
                    ├─ !MBEDTLS_PLATFORM_MEMORY          → #define to calloc / free          (platform.h:163-167)
                    ├─ MEMORY + CALLOC_MACRO + FREE_MACRO → #define to your macros              (platform.h:139-145)
                    └─ MEMORY, no macros                  → real functions in platform.c:47-54
                                                            → *mbedtls_calloc_func / *mbedtls_free_func
                                                            (default: MBEDTLS_PLATFORM_STD_* = calloc/free,
                                                             or platform_calloc_uninit → always NULL)
```

The grep found no direct `malloc`/`calloc`/`free` calls in `library/` apart from comments and one `free(hdr->trace)` in `memory_buffer_alloc.c:404`, which sits in the `MBEDTLS_MEMORY_BACKTRACE` debug path. I did not check the matching allocation there. About 48 library files call `mbedtls_calloc`/`mbedtls_free`.

## How a project substitutes its allocator

Set `MBEDTLS_PLATFORM_MEMORY` in the config, then pick one of three options:

| Option | Config | Notes |
|---|---|---|
| **Compile-time macros** | `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free`, both required | Zero indirection. Macros win over runtime setup (`platform.c:16-19`). |
| **Runtime** | Leave both macros undefined, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` early | Always returns 0 and does no NULL checks. |
| **Compile-time function names** | `MBEDTLS_PLATFORM_STD_CALLOC` / `STD_FREE`, optionally with `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` | Used to avoid libc, as in `tests/configs/user-config-malloc-0-null.h:21` (`custom_calloc`). |

`check_config.h:558-573` enforces the pairing rules: the two macros must be set together, and `*_MACRO` and `STD_*` are mutually exclusive for each function.

Requirements the code actually imposes on a substitute:
- **`free(NULL)` must be safe.** `mbedtls_zeroize_and_free` (`platform_util.c:139-146`) only guards the zeroize step and calls `mbedtls_free(buf)` unconditionally.
- **calloc semantics.** The doc (`mbedtls_config.h:4113-4124`) says the replacement should behave like `calloc`, and the library relies on zeroed memory from it. I did not verify every call site.
- **Set it before any allocation.** The function pointers are plain statics with no synchronisation (`platform.c:44-61`). Swapping them mid-session also breaks any memory already allocated by the old allocator, since it must be freed by the same one. That is my reading of the code, not something the docs state.

## What the library does with the facility

**Allocation.** The library uses `mbedtls_calloc` for object and buffer creation:
- TLS: peer certificate copies, session tickets and buffer resizing (`ssl_tls.c:251-322`).
- Bignum limbs and exponentiation scratch (`bignum.c:218, 266, 1654, 1789`).
- X.509, PSA, and others.

On failure it returns a module-specific error such as `MBEDTLS_ERR_SSL_ALLOC_FAILED` or `MBEDTLS_ERR_MPI_ALLOC_FAILED`, rather than aborting.

**Freeing secrets.** Key and secret material goes through `mbedtls_zeroize_and_free` (`platform_util.c:139`), which zeroes the buffer and then calls `mbedtls_free`. Examples are RSA signature scratch, PEM and PK parsing buffers, PSA key slots and the SSL session cache. Because the free path also goes through the substitute, a custom allocator still sees these frees.

**A built-in substitute uses the same hook.** `library/memory_buffer_alloc.c` provides a heap over a caller-supplied static buffer. `mbedtls_memory_buffer_alloc_init()` (`:566-576`) calls `mbedtls_platform_set_calloc_free` itself, using a mutex-wrapped variant when `MBEDTLS_THREADING_C` is on. The sample programs (`ssl_server2`, `ssl_client2`, `benchmark`, `selftest`) use this path.

The practical consequence is that the last caller of `mbedtls_platform_set_calloc_free` wins. Enabling the buffer allocator silently replaces a project's runtime allocator, and I did not check whether `mbedtls_memory_buffer_alloc_free()` restores the defaults.