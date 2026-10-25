## Short answer

Every allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`. Those two functions do not call libc directly. They call through two file-static function pointers, and the embedding project can replace those pointers at runtime or at build time.

## What gets called

```
library code (e.g. aes_ctx_alloc, ecp_mul_comb, ssl_*)
   └─ mbedtls_calloc(n, size)            library/platform.c:47
        └─ (*mbedtls_calloc_func)(n, size)   platform.c:44 (static pointer)
             └─ default: calloc (or a stub that returns NULL)

library code
   └─ mbedtls_free(ptr)                  library/platform.c:52
        └─ (*mbedtls_free_func)(ptr)         platform.c:45 (static pointer)
```

- `mbedtls_calloc_func` is initialised to `MBEDTLS_PLATFORM_STD_CALLOC`, and `mbedtls_free_func` to `MBEDTLS_PLATFORM_STD_FREE` (`platform.c:44-45`).
- `MBEDTLS_PLATFORM_STD_CALLOC` is defined as `calloc` in `include/mbedtls/platform.h:84`, unless `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set. In `library/platform.c:24-33` there is a branch that maps it to `platform_calloc_uninit`, which returns NULL. I read that as the no-std-functions case, but the index does not show the exact polarity of that gate, so check it in the source.
- Call sites never name `mbedtls_calloc` directly in the header. `platform.h` maps the name at compile time. The index lists two `mbedtls_calloc` macro rows: one at `platform.h:144` expands to `MBEDTLS_PLATFORM_CALLOC_MACRO`, and one at `platform.h:167` expands to plain `calloc`. The rows are gated on `MBEDTLS_PLATFORM_MEMORY`, and the index does not confirm which branch is `#if` and which is `#else`.

## How a project substitutes its own allocator

There are three routes. The index confirms all three.

| Route | Mechanism | Evidence in the index |
|---|---|---|
| **Compile-time macros** | Enable `MBEDTLS_PLATFORM_MEMORY` and define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`. `mbedtls_calloc` then expands to your function. | `platform.h:138-145`. The test config `tests/configs/user-config-malloc-0-null.h` uses a `custom_calloc` symbol. |
| **Runtime pointer swap** | Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` at startup. This overwrites the two static pointers and returns 0. | `library/platform.c:57-63`. |
| **Build with no std functions** | Set `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS`, which removes the `calloc`/`free` defaults. The library then needs an explicit substitute, or it gets the NULL-returning stub. | `platform.h:57-115`, `platform.c:24-33`. |

The macro route is the only one that resolves at compile time. The runtime route changes global state, so it must happen before any library object is created.

The index also contains a `component_test_platform_calloc_macro` in `tests/scripts/components-configuration-platform.sh`, which exercises the macro route in CI.

## What the library itself does with the facility

The library ships a stack-based allocator, `mbedtls_memory_buffer_alloc_init(buf, len)` in `library/memory_buffer_alloc.c:566-600`. A project calls it once with a static buffer. It then:

1. Zeroes its private heap context and, when `MBEDTLS_THREADING_C` is defined, initialises a mutex.
2. Calls `mbedtls_platform_set_calloc_free(buffer_alloc_calloc_mutexed, buffer_alloc_free_mutexed)`, or the non-mutex pair if threading is off. The library's own allocator is now the function behind `mbedtls_calloc`.
3. Aligns the buffer, zeroes it, and writes the first block header with two magic values.

Its doc comment says it "does not call calloc() and free()". Callers of `mbedtls_calloc` are spread across the whole library: about 150 AST-resolved call sites, including the cipher context allocators, ECP, ASN.1, PSA key slots, and the SSL and X.509 parsers. `mbedtls_free` has a similar count.

## Points to verify

- The `#if`/`#else` polarity of `platform.h:163-168` and `platform.c:24-33` is not settled by the index. Read those blocks before relying on them.
- The shipped default of `MBEDTLS_PLATFORM_MEMORY` is not in the index. The index has no config header for this target.
- `MBEDTLS_PLATFORM_CALLOC_MACRO` and `FREE_MACRO` have no definition site in the index. The index reads that as "commented out in `mbedtls_config.h`, default off", which fits how the macro route is opt-in.