## What gets called

The library never calls `malloc`, `calloc` or `free` directly. Every dynamic allocation goes through `mbedtls_calloc()` and `mbedtls_free()`. A grep of `library/*.c` finds about 363 uses of those two names, and the only raw `calloc`/`free` hits are in comments. I did not check `programs/` or `tests/` for raw calls.

What `mbedtls_calloc` resolves to depends on configuration (`include/mbedtls/platform.h:138-168`):

| Config | `mbedtls_calloc` / `mbedtls_free` |
|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (the default, `mbedtls_config.h:208`) | Macros for libc `calloc` / `free` |
| `MBEDTLS_PLATFORM_MEMORY` on, plus `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | Macros expanding to your functions, resolved at compile time |
| `MBEDTLS_PLATFORM_MEMORY` on, macros not both defined | Real functions in `library/platform.c` that call through function pointers, which default to `MBEDTLS_PLATFORM_STD_CALLOC/FREE` |

The two macros must be defined together (`check_config.h:558-573`).

## How a project substitutes its allocator

**Compile time.** Enable `MBEDTLS_PLATFORM_MEMORY` and define both macros, for example `-DMBEDTLS_PLATFORM_CALLOC_MACRO=my_calloc -DMBEDTLS_PLATFORM_FREE_MACRO=my_free`. Every call site then expands to your function. No runtime setter is involved.

**Runtime.** Enable only `MBEDTLS_PLATFORM_MEMORY` and call the setter once, before any other library call:

```c
static void *my_calloc(size_t n, size_t sz) { return pool_alloc(n * sz); }
static void my_free(void *p)                { pool_release(p); }

mbedtls_platform_set_calloc_free(my_calloc, my_free);
```

`platform.c:57-61` stores the two pointers in file-scope globals and does nothing else. There is no locking, no validation and no reporting of failure.

**Defaults when the project does not set them.** Without `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` the pointers default to libc. With `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` they default to stubs: `calloc` returns NULL and `free` does nothing (`platform.c:24-42`). A project that forgets the setter on such a target gets NULL from its first allocation, which the library reports as an allocation failure.

**Caveats.** The allocator is process-global, not per-context. Changing it while memory from the old allocator is still live is unsafe; that follows from the design, and I did not test it. `mbedtls_platform_setup()` and `mbedtls_platform_teardown()` are no-op hooks by default (`platform.c:386-400`) and do not touch the allocator.

## What the library does with the facility

The library ships its own allocator, `library/memory_buffer_alloc.c`. It is the only in-tree user of the setter:

- `mbedtls_memory_buffer_alloc_init(buf, len)` takes a caller-supplied buffer and calls `mbedtls_platform_set_calloc_free(...)` with its own `buffer_alloc_calloc` / `buffer_alloc_free` (`memory_buffer_alloc.c:566-600`). With `MBEDTLS_THREADING_C` it installs mutex-wrapped variants. From then on, all library allocations come from that buffer and no libc heap is used.
- The allocator keeps size and magic-number headers and a free list, and checks for corruption. Failures are reported to stderr as `FATAL:` lines (for example, `memory_buffer_alloc.c:373`).
- `mbedtls_memory_buffer_alloc_free()` (`memory_buffer_alloc.c:602-607`) destroys the mutex and zeroes the heap state. It does **not** restore the default function pointers. By reading the code, the global pointers still point at `buffer_alloc_calloc` after teardown, now operating on a zeroed heap. Any library call after teardown should fail or misbehave. I have not run that path to confirm it. A project that tears this allocator down must reinstall its own allocator, or avoid calling into the library afterwards.