## What actually gets called

Every allocation in mbedtls goes through two thin wrapper functions in `library/platform.c`, gated by `MBEDTLS_PLATFORM_C`/`MBEDTLS_PLATFORM_MEMORY`:

```c
void *mbedtls_calloc(size_t nmemb, size_t size) { return (*mbedtls_calloc_func)(nmemb, size); }
void  mbedtls_free(void *ptr)                   { (*mbedtls_free_func)(ptr); }
```

These aren't the allocator itself — they indirect through two static function pointers:

```c
static void *(*mbedtls_calloc_func)(size_t, size_t) = MBEDTLS_PLATFORM_STD_CALLOC;
static void  (*mbedtls_free_func)(void *)           = MBEDTLS_PLATFORM_STD_FREE; /* not shown above but symmetric */
```

`MBEDTLS_PLATFORM_STD_CALLOC` is a config-controlled default (the index has no definition site for `MBEDTLS_PLATFORM_CALLOC_MACRO`/`MBEDTLS_PLATFORM_FREE_MACRO` themselves — those are conditionally-compiled hooks the repo doesn't define by default, so read `include/mbedtls/platform.h` to confirm the shipped default, but the wired path resolves to libc `calloc`/`free` unless overridden).

Every one of the ~140 call sites across the library — RSA, ECP, SSL session handling, X.509 parsing, PSA key slots, ASN.1, etc. — calls `mbedtls_calloc`/`mbedtls_free`, never `malloc`/`free` directly. `dossier` confirms this: the caller list for `mbedtls_calloc` is exhaustively the library's own internal allocators (`aes_ctx_alloc`, `ecdsa_rs_alloc`, `mbedtls_ssl_setup`, `mbedtls_x509_crt_parse_der_internal`, etc.), plus one self-test (`calloc_self_test`) and one macro (`ALLOC` in `md.c`) that wraps it for per-algorithm context allocation.

There's also a compile-time alternative path: `include/mbedtls/platform.h` defines `mbedtls_calloc`/`mbedtls_free` as raw macros expanding to `calloc`/`free` when `MBEDTLS_PLATFORM_MEMORY` is *not* set — that's the "no runtime indirection" build configuration, used by e.g. `programs/test/udp_proxy.c`.

## How a project substitutes its own allocator

Two independent mechanisms, and they don't compose the same way:

1. **Runtime substitution (function pointers).** With `MBEDTLS_PLATFORM_MEMORY` enabled, call `mbedtls_platform_set_calloc_free()`:
   ```c
   int mbedtls_platform_set_calloc_free(void *(*calloc_func)(size_t, size_t),
                                         void (*free_func)(void *))
   {
       mbedtls_calloc_func = calloc_func;
       mbedtls_free_func = free_func;
       return 0;
   }
   ```
   This just repoints the two static function pointers — every subsequent `mbedtls_calloc`/`mbedtls_free` call in the library goes to the new functions immediately, with no rebuild needed. This is the mechanism for e.g. bare-metal targets with a custom heap, RTOS-specific allocators, or memory-tracking wrappers.

2. **Compile-time macro override.** With `MBEDTLS_PLATFORM_MEMORY` *not* set, `mbedtls_calloc`/`mbedtls_free` are preprocessor macros — a project can `#define MBEDTLS_PLATFORM_CALLOC_MACRO my_calloc` (and the FREE equivalent) in its config header, and the library's ~140 call sites are rewritten to call that symbol directly, no indirection through function pointers at all.

## What the library itself does with the facility

The one first-party consumer of `mbedtls_platform_set_calloc_free` in this repo is `mbedtls_memory_buffer_alloc_init()` (`include/mbedtls/memory_buffer_alloc.h` / `library/memory_buffer_alloc.c`) — mbedtls's own bundled stack-based allocator. Its `dossier` brief states it directly: it does memory management inside a caller-supplied static buffer and does *not* call `calloc()`/`free()`; instead it calls `mbedtls_platform_set_calloc_free()` to install its own `buffer_alloc_calloc`/`buffer_alloc_free` (via mutexed wrapper variants) as the global allocator.

Those functions implement a real allocator on top of the fixed buffer: a first-fit walk over a free list (`heap.first_free`), block splitting when a found block is larger than needed plus a header, and on free, coalescing with the physically adjacent previous/next block before re-inserting into the free list. They include their own consistency checks — `verify_header`/`verify_chain` guard against corruption and call `mbedtls_exit(1)` on a fatal mismatch (double-free, free of unallocated memory, or free outside the managed buffer) — and, under `MBEDTLS_MEMORY_DEBUG`/`MBEDTLS_MEMORY_BACKTRACE`, track allocation counts, high-water mark, and captured backtraces per block.

So the "substitution facility" isn't just a theoretical hook for downstream projects — mbedtls uses the exact same mechanism internally to swap libc's heap out for a deterministic, buffer-bounded allocator suitable for constrained/embedded targets where a general-purpose heap is undesirable. A project embedding mbedtls has the identical lever available to plug in its own allocator (a pool allocator, a tracked/guarded allocator for fuzzing, an RTOS heap, etc.) with no changes to any of the ~140 call sites.
