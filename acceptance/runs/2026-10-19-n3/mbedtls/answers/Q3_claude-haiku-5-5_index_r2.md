**Short answer:** library code never calls the C library's `calloc`/`free` directly. Every allocation goes through `mbedtls_calloc()` and `mbedtls_free()`, which forward to function pointers that a project can replace at build time or at runtime.

## The call chain

```
library code  ->  mbedtls_calloc(n, sz)  ->  mbedtls_calloc_func(n, sz)  ->  calloc / your allocator
                  (library/platform.c:47)    (static fn pointer,           
                                              platform.c:44)
```

- `mbedtls_calloc` and `mbedtls_free` (`library/platform.c:47-55`) are thin wrappers that dereference `mbedtls_calloc_func` and `mbedtls_free_func`.
- The pointers are initialized to `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` (`platform.c:44-45`).
- Those two macros default to `platform_calloc_uninit` (always returns NULL) and `platform_free_uninit` (no-op) when the project doesn't define them (`platform.c:24-42`). So an unconfigured build fails allocations cleanly rather than calling libc.
- In `include/mbedtls/platform.h:138-168`, the public names are either macros or real functions:
  - If `MBEDTLS_PLATFORM_MEMORY` is on and both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` are defined, `mbedtls_calloc`/`mbedtls_free` become those macros. There is no indirection and no runtime hook.
  - If `MBEDTLS_PLATFORM_MEMORY` is on but the macros aren't, they are real functions plus the setter.
  - If `MBEDTLS_PLATFORM_MEMORY` is off, they are `#define`d straight to libc `calloc` and `free` (`platform.h:163-168`).

## How a project substitutes its allocator

Two routes, both documented in `include/mbedtls/mbedtls_config.h:155-215` and `:4113-4151`:

1. **Compile time (no indirection).** Set in the project's config:
   ```c
   #define MBEDTLS_PLATFORM_MEMORY
   #define MBEDTLS_PLATFORM_CALLOC_MACRO  my_calloc
   #define MBEDTLS_PLATFORM_FREE_MACRO    my_free
   ```
   Both macros must be defined together; defining only one is not valid. `platform.c` drops its runtime code entirely in this case (`platform.c:20-22`).

2. **Runtime (function pointers).** Enable `MBEDTLS_PLATFORM_MEMORY` and leave the macros undefined. Then either:
   - define `MBEDTLS_PLATFORM_STD_CALLOC`/`MBEDTLS_PLATFORM_STD_FREE` as the default allocator (e.g. `calloc`/`free`), or
   - call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before using the library (`platform.c:57-63`, declared in `platform.h:160-161`). This simply stores both pointers in the globals.

   The setter does no locking and no validation. It has to run before any other thread touches the library.

## What the library does with the facility

- **Everything routes through it.** A grep of `library/` for raw `calloc(`/`free(` turns up no allocation calls outside the platform layer. Only `memory_buffer_alloc.c:404` calls libc `free` directly (on the debug backtrace array, `hdr->trace`). That is worth checking if you want a pure custom heap, since it bypasses the hook.
- **The library ships its own substitute.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566-600`) takes a caller-supplied buffer and turns it into a heap. It zeros the buffer and sets up one header, then calls `mbedtls_platform_set_calloc_free(buffer_alloc_calloc_mutexed, buffer_alloc_free_mutexed)` (or the unmutexed pair if `MBEDTLS_THREADING_C` is off). From then on, every library allocation is served from that buffer and never touches `malloc`. This is a runtime substitution done by the library itself, and it is the reference example for a custom allocator.
- **The library's own tests use the hook too.** `memory_buffer_alloc.c:660-728` calls `mbedtls_calloc` directly to test exhaustion and fragmentation.
- **Fallback behavior.** With no allocator configured, `mbedtls_calloc` returns NULL and `mbedtls_free` does nothing. Library code that allocates must therefore handle NULL, and a missing allocator shows up as an allocation failure rather than a crash or a silent libc call.

## Things to watch when substituting

- A custom allocator must be installed before the first library call, since there is no synchronization on the function pointers.
- Only `calloc`-style semantics are expected (zeroed memory, `nmemb * size` overflow checking is the allocator's job). Use `MBEDTLS_PLATFORM_STD_*` only for allocators with that signature.
- The debug trace in `memory_buffer_alloc.c` bypasses the hook, so a fully custom heap should not rely on that option.

I did not build or run anything for this; the answer comes from reading the source and the index.