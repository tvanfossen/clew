Mbed TLS never calls `malloc` or `calloc` directly. Every allocation goes through two functions, `mbedtls_calloc()` and `mbedtls_free()`, and what those two resolve to depends on the build configuration.

**What gets called**

| Config | `mbedtls_calloc` resolves to | Evidence |
|---|---|---|
| `MBEDTLS_PLATFORM_MEMORY` off (the shipped default) | libc `calloc`, by macro | `include/mbedtls/platform.h:163-167`; `MBEDTLS_PLATFORM_MEMORY` is commented out at `mbedtls_config.h:208` |
| On, plus both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` | Your function, named at compile time | `platform.h:138-144` |
| On, macros undefined | A function pointer, set at runtime | `platform.h:145-161`; `library/platform.c:44-63` |

In the runtime case, `library/platform.c` holds two static function pointers, `mbedtls_calloc_func` and `mbedtls_free_func`. `mbedtls_calloc()` and `mbedtls_free()` simply dereference them. Their initial values are `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE`, which default to stubs (`platform_calloc_uninit` returns NULL, `platform_free_uninit` does nothing). So with `MBEDTLS_PLATFORM_MEMORY` on and nothing installed, every allocation fails. The header comment states this explicitly.

**How a project substitutes its allocator**

Option A, compile time. Define both macros in your user config (`MBEDTLS_USER_CONFIG_FILE`, or your own `mbedtls_config.h`):

```c
#define MBEDTLS_PLATFORM_MEMORY
#define MBEDTLS_PLATFORM_CALLOC_MACRO  my_calloc
#define MBEDTLS_PLATFORM_FREE_MACRO    my_free
```

Both macros must be defined together, or neither. The macros take precedence over the runtime setter, and `platform.c` drops its pointer code entirely in that case.

Option B, runtime. Define only `MBEDTLS_PLATFORM_MEMORY`, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` before any other Mbed TLS call. The setter is a plain pointer assignment with no lock, so call it during startup, before any threads exist. The contract for the functions you supply is in `mbedtls_config.h:4118-4133`: `calloc` must return NULL on failure, `free(NULL)` must be a no-op, and a non-null pointer must have come from your calloc and not yet be freed.

**What the library does with the facility**

- All library allocations go through `mbedtls_calloc`/`mbedtls_free`. A grep for raw `malloc`/`calloc`/`realloc`/`free` calls under `library/` found none. The only hits were in comments, plus one `free(hdr->trace)` in `memory_buffer_alloc.c:404`, which I did not check.
- The library provides its own allocator in `library/memory_buffer_alloc.c`, a first-fit allocator over one caller-supplied buffer. Its init, `mbedtls_memory_buffer_alloc_init()` (line 566), zeroes the static heap, sets the calloc/free pair to its own functions through `mbedtls_platform_set_calloc_free()` (lines 572 and 575), and writes the first block header. This is the only place the library installs an allocator itself. It uses one static heap per process, so a second init overwrites the first.
- The buffer allocator adds a mutex when `MBEDTLS_THREADING_C` is on, and its free path checks block magic values. The `FATAL: mbedtls_free() on unallocated` messages (lines 373 and 390) show it detects wild frees.
- Tests and programs use the hook too. `tests/scripts/components-configuration-crypto.sh` has a component where the test code can use calloc/free but the core library cannot, which checks that no direct heap use leaked into the library. `programs/test/query_config.c` lists the setter.

Not checked: whether the `MBEDTLS_PLATFORM_MEMORY` build is exercised in the default CI, and the exact trace allocation at line 404.