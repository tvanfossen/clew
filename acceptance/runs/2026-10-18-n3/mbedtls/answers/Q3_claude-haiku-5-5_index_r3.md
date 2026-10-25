In mbedtls, every library allocation goes through two public names, `mbedtls_calloc()` and `mbedtls_free()`, and what they reach depends on how the library was built. The resolution happens in `include/mbedtls/platform.h` and `library/platform.c`.

**What gets called**

| Build configuration | `mbedtls_calloc` resolves to | `mbedtls_free` resolves to |
|---|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off | libc `calloc` (via macro, `platform.h:166-167`) | libc `free` |
| `MBEDTLS_PLATFORM_MEMORY` on, both `MBEDTLS_PLATFORM_{CALLOC,FREE}_MACRO` defined | that macro, expanded at compile time (`platform.h:139-144`) | that macro |
| `MBEDTLS_PLATFORM_MEMORY` on, macros not defined | `mbedtls_calloc()` function, which calls through a static function pointer | `mbedtls_free()`, which calls through a static function pointer |

In the third row, `platform.c:44-45` initialises the pointers to `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. If the user has not defined those, `platform.c:24-42` substitutes stubs that fail. `platform_calloc_uninit` returns NULL and `platform_free_uninit` does nothing. So an unconfigured runtime allocator fails cleanly rather than crashing.

Inside the library, the call sites just write `mbedtls_calloc(...)` and `mbedtls_free(...)`. The index shows about 150 functions calling `mbedtls_calloc` directly, from `aes_ctx_alloc` and `ecp_mul_comb` up through the SSL and X.509 code. `mbedtls_zeroize_and_free` (`library/platform_util.c:139`) zeroizes a buffer and then calls `mbedtls_free`.

**How a project substitutes its allocator**

Two routes:

1. **Compile time (no runtime cost).** Enable `MBEDTLS_PLATFORM_MEMORY` and define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in the user config, or in a header pulled in by `MBEDTLS_USER_CONFIG_FILE`. Both must be set together. The header then maps to the project's functions. The calls are direct, with no indirection.

2. **Runtime.** Enable `MBEDTLS_PLATFORM_MEMORY` without the macros. Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other mbedtls call (`platform.c:57-63`). It just stores the two pointers in the static variables. The `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` macros let you pick the defaults without calling the setter.

The config docs in `mbedtls_config.h:155-203` and `4113-4133` specify the contract. `calloc` must zero the memory. A zero-size request may return NULL or a valid pointer. `free(NULL)` must be a no-op. A non-NULL pointer passed to `free` must be one the allocator returned and that hasn't been freed yet. The setter is global, so it is not per-context, and the pointers are not guarded by a lock. The code does not check thread-safety for you.

**What the library itself does with the facility**

The library ships its own allocator behind the same hook, `library/memory_buffer_alloc.c`. `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) takes a caller-supplied buffer and manages it as a heap. It zeroes the buffer and sets up one free block. It then calls `mbedtls_platform_set_calloc_free(buffer_alloc_calloc_mutexed, buffer_alloc_free_mutexed)`, or the unmutexed pair if `MBEDTLS_THREADING_C` is off. Every later `mbedtls_calloc` and `mbedtls_free` is served from that buffer, with no libc involved. The same mechanism is what makes the buffer allocator usable on bare-metal targets with no heap.

Things to be aware of:

- The buffer allocator changes global state. Calling `mbedtls_memory_buffer_alloc_init` silently redirects every mbedtls allocation in the process, and it is not reset by free or `mbedtls_memory_buffer_alloc_free`. Any custom allocator set earlier is overwritten.
- The index also shows `component_test_psa_crypto_without_heap` in `tests/scripts/components-configuration-crypto.sh`. It builds a configuration where the test code can use calloc/free but the core library cannot. That is the supported way to verify that a no-heap build really has no hidden allocations.
- I did not read `memory_buffer_alloc.c`'s internal `buffer_alloc_calloc`/`buffer_alloc_free` bodies or the mutex wrapper, so I have not verified their details.