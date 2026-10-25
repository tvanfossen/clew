**Short answer:** library code never calls `calloc`/`free` directly. It calls `mbedtls_calloc()` and `mbedtls_free()`, which dispatch through two static function pointers in `library/platform.c`. Those pointers default to the C standard functions and can be replaced at runtime or at compile time.

**What gets called**

```
library code (e.g. ssl_setup, mbedtls_mpi_grow, x509 parsing)
   │  mbedtls_calloc(n, size)  /  mbedtls_free(p)
   ▼
library/platform.c:47  mbedtls_calloc()  → (*mbedtls_calloc_func)(n, size)
library/platform.c:52  mbedtls_free()    → (*mbedtls_free_func)(p)
   ▲
library/platform.c:44-45  static mbedtls_calloc_func = MBEDTLS_PLATFORM_STD_CALLOC
                          static mbedtls_free_func   = MBEDTLS_PLATFORM_STD_FREE
```

Callers resolve to `mbedtls_calloc`/`mbedtls_free` across the library: the context allocators for AES, GCM, CCM and others, the MPI and ECP code, the X.509 and PKCS#7 parsers, the SSL handshake and session code, and the PSA key-slot code.

**How a project substitutes its own allocator**

There are two routes.

1. **Compile time: `MBEDTLS_PLATFORM_MEMORY`.** Define this in the project's config. It enables the `platform.h` branch at lines 138–168 that uses the replacement macros. Then define `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` to your functions. The `mbedtls_calloc` and `mbedtls_free` macros at `platform.h:144` and `:143` expand to them. Both macros default to off in `include/mbedtls/mbedtls_config.h:4150-4151`, and the index has no definition site for either in the repo, so the project must supply them. I could not read the exact `#if` expressions at `platform.h:139-145`, so I'm inferring the branch structure from the gate records.

2. **Run time: `mbedtls_platform_set_calloc_free(calloc_func, free_func)`** (`library/platform.c:57-63`). This stores the two pointers. It is the hook for a project that wants to pick an allocator at startup, or to install one of the library's own allocators.

The default `MBEDTLS_PLATFORM_STD_CALLOC` is `calloc` at `include/mbedtls/platform.h:84`. If the standard functions are disabled, `platform_calloc_uninit` in `library/platform.c:25-30` is the fallback, and it returns `NULL` every time.

**What the library does with the facility itself**

The library's own stack-based allocator in `library/memory_buffer_alloc.c` uses it.

- `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) zeroes its heap context. It then calls `mbedtls_platform_set_calloc_free` to install its own allocator. The threaded build installs `buffer_alloc_calloc_mutexed` and `buffer_alloc_free_mutexed`, and the non-threaded build installs `buffer_alloc_calloc` and `buffer_alloc_free`. The buffer is aligned and carved into one initial free block.
- `buffer_alloc_calloc_mutexed` (`memory_buffer_alloc.c:541-552`) takes the heap mutex around the real allocation, so it is thread-safe when `MBEDTLS_THREADING_C` is set.
- `mbedtls_memory_buffer_alloc_free` (declared in `include/mbedtls/memory_buffer_alloc.h`) frees the mutex and clears the heap.

So a project that wants a fixed-pool allocator with no heap can call `mbedtls_memory_buffer_alloc_init` once at startup and never touch `calloc`. The library then allocates from that buffer through the same two hooks.

**Caveats**

- Library-internal allocations and the replaceable hooks are tied together. Whichever allocator is installed last wins, so mixing the compile-time macros with a later `mbedtls_platform_set_calloc_free` call overrides the macros.
- `mbedtls_memory_buffer_alloc_init` is a global one-shot. It is not a per-context allocator.
- The index does not show a `mbedtls_platform_set_calloc_free` declaration in `platform.h`. Its presence in the public API is inferred from its use by `memory_buffer_alloc.c`.