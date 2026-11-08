In the default build, `mbedtls_calloc` and `mbedtls_free` are not functions the library defines. They are macros that expand to the C library's `calloc` and `free`. Every allocation in the library goes through those two names, and the way they resolve depends on three config options.

**What gets called**

| Config | `mbedtls_calloc` resolves to | Source |
|---|---|---|
| `MBEDTLS_PLATFORM_MEMORY` undefined (the default, `mbedtls_config.h:208` is commented out) | `calloc` | `platform.h:166-167` |
| `MBEDTLS_PLATFORM_MEMORY` + both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | whatever those macros name, fixed at compile time | `platform.h:139-144` |
| `MBEDTLS_PLATFORM_MEMORY` alone | a function pointer, set at runtime | `platform.h:148-161`, `platform.c:44-61` |

In the runtime case, `platform.c` holds two static function pointers, `mbedtls_calloc_func` and `mbedtls_free_func`. The public `mbedtls_calloc()` and `mbedtls_free()` just dereference them. The initial values are `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`. Those default to `calloc` and `free` unless `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is set, in which case they are stubs: calloc returns NULL and free does nothing (`platform.c:25-42`).

**How a project substitutes its allocator**

Two routes:

1. **Compile time.** Define `MBEDTLS_PLATFORM_MEMORY`, `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`, pointing the macros at your functions. The library then calls them directly, with no indirection. The config checks require the two macros to be defined together (`check_config.h:558-573`).
2. **Runtime.** Define only `MBEDTLS_PLATFORM_MEMORY`, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any allocation. This function exists only in this mode. In macro mode it is not declared and not compiled, so calling it fails to link.

Either way, the contract from `mbedtls_config.h:4113-4132` is the same. Your calloc must zero the memory and return NULL on failure. Your free must accept NULL and must only receive pointers your calloc returned. The setter in `platform.c` does no locking, so call it once at startup before threads start.

**What the library does with the facility**

The library's own allocator, `memory_buffer_alloc.c`, is a consumer of this mechanism. `mbedtls_memory_buffer_alloc_init(buf, len)` carves allocations out of a caller-supplied static buffer. It then calls `mbedtls_platform_set_calloc_free()` to install its own calloc and free as the global pointers (`memory_buffer_alloc.c:566-576`). When `MBEDTLS_THREADING_C` is enabled, it wraps both in a mutex. Note that this is a process-wide switch. Any later allocation in the program uses the heap, and a second init replaces it. Using both a custom allocator and this one at once is not possible, since they share the same global pointers.

The rest of the library calls only `mbedtls_calloc` and `mbedtls_free`. A grep of `library/` found no direct `malloc`, `calloc` or `free` calls, apart from one `free(hdr->trace)` in `memory_buffer_alloc.c:404`. That call is on the debug backtrace field, not a library allocation, and I did not check the `#if` guard around it. Allocation failures are handled by the caller, and `mbedtls_calloc` returning NULL is the normal failure signal.

One thing I did not check: whether the build used for these runs enables `MBEDTLS_PLATFORM_MEMORY` or `MBEDTLS_MEMORY_BUFFER_ALLOC_C`. The defaults in `mbedtls_config.h` leave both disabled.