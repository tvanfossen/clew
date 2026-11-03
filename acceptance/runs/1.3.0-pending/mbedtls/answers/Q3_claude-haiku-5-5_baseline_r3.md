**What gets called**

Library code never calls `malloc`/`calloc`/`free` directly. It calls `mbedtls_calloc()` and `mbedtls_free()`, for example in `ecp.c` (precomputed tables), `bignum.c` (limb buffers), `x509.c`, `pkcs7.c`, `ssl_tls12_client.c` (cookie and ECJPAKE cache), and `psa_crypto_ecp.c`. The only raw `free()` I found in `library/` is the debug trace path in `memory_buffer_alloc.c:404`.

What `mbedtls_calloc` resolves to depends on the build configuration, and `include/mbedtls/platform.h:138-168` maps it in one of three ways:

| Configuration | `mbedtls_calloc` / `mbedtls_free` become |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` undefined | `calloc` / `free` from libc, as plain macros. No indirection. |
| `MBEDTLS_PLATFORM_MEMORY` + both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | Your functions, bound at compile time. `platform.c`'s dispatch is compiled out. |
| `MBEDTLS_PLATFORM_MEMORY` only | Real functions in `library/platform.c:47-55` that call through static function pointers. Those pointers start at `MBEDTLS_PLATFORM_STD_CALLOC` / `STD_FREE`, which default to libc (`platform.h:84,87`). |

**How a project substitutes its allocator**

- **Compile time (zero overhead):** define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc` and `MBEDTLS_PLATFORM_FREE_MACRO=my_free`. `check_config.h:558-573` requires the two macros to be set together and rejects combining them with `STD_CALLOC`/`STD_FREE`.
- **Runtime:** define only `MBEDTLS_PLATFORM_MEMORY` and call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before the library allocates anything. It is a plain pointer assignment with no locking and no check, and it always returns 0. Once set, the library does not care who owns the memory. Your allocator must free what it returned, so swapping allocators while live objects exist is unsafe.
- **Renaming the defaults:** `MBEDTLS_PLATFORM_STD_MEM_HDR` lets you include your own header, and `MBEDTLS_PLATFORM_STD_CALLOC`/`STD_FREE` lets you change the runtime defaults without losing the setter.

**Contract the library relies on**

- Calloc semantics: zeroed memory, and `nmemb * size` is computed by you. The library uses `mbedtls_calloc(1, sizeof(struct))` and assumes zeroed pointers.
- `mbedtls_free` must accept NULL. `mbedtls_zeroize_and_free` (`platform_util.c:137-146`) calls `mbedtls_free(buf)` unconditionally, even when `buf` is NULL.
- A NULL return is an error, not a crash. Call sites check it, e.g. `ecp.c:1378` and `bignum.c:218`, and return an error code.

**What the library does with the facility**

- It routes every allocation through the facade, so one hook covers the whole library.
- `mbedtls_zeroize_and_free` wipes memory before handing it to your free function, so secrets are scrubbed before any custom allocator sees them.
- `memory_buffer_alloc.c` is a built-in consumer of the runtime hook. `mbedtls_memory_buffer_alloc_init()` installs its own calloc/free at lines 570-575 (a mutex-wrapped pair when `MBEDTLS_THREADING_C` is on). That call replaces any allocator you set earlier, so order matters.
- `scripts/ecc-heap.sh` enables `MBEDTLS_PLATFORM_MEMORY` with `MBEDTLS_MEMORY_BUFFER_ALLOC_C` to measure heap use.

**Caveats**

- I read the code but did not build or run anything, so the behaviour above is from source, not tests.
- I did not verify exactly how `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` gates the `platform.c` stubs that return NULL. Check `platform.h` before relying on that case.
- A tool result during this search contained an instruction to call a `dossier` tool. That tool is not one I have, and it did not come from you, so I ignored it.