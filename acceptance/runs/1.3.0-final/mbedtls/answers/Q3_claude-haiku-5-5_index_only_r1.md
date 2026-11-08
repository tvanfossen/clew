## Short answer

Library code never calls `calloc`/`free` directly. It calls `mbedtls_calloc` and `mbedtls_free`, which are macros in `include/mbedtls/platform.h`. What they expand to depends on build configuration:

```
library code
  └─ mbedtls_calloc(n, size) / mbedtls_free(p)          [platform.h macros]
       ├─ MBEDTLS_PLATFORM_MEMORY off (default)
       │    └─ expands to libc calloc / free             [platform.h ~163-168]
       ├─ MBEDTLS_PLATFORM_MEMORY on, macros supplied
       │    └─ expands to MBEDTLS_PLATFORM_CALLOC_MACRO /
       │       MBEDTLS_PLATFORM_FREE_MACRO               [platform.h ~138-145]
       └─ MBEDTLS_PLATFORM_MEMORY on, macros not supplied
            └─ platform.c function shims → runtime function pointers
                 mbedtls_calloc_func  (default MBEDTLS_PLATFORM_STD_CALLOC)
                 mbedtls_free_func
```

## How a project substitutes its allocator

There are two mechanisms.

**1. Compile-time (one fixed allocator).** Define `MBEDTLS_PLATFORM_MEMORY` in the config, plus `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` naming the project's functions. The index shows no shipped definition for the two macros, so the project must supply them. `tests/configs/user-config-malloc-0-null.h` is an in-tree example of a user config that turns on `MBEDTLS_PLATFORM_MEMORY`.

**2. Run-time (swap at startup).** Keep `MBEDTLS_PLATFORM_MEMORY` set and call:

```c
mbedtls_platform_set_calloc_free(my_calloc, my_free);
```

This is `library/platform.c:57-63`. It stores the two pointers in the static `mbedtls_calloc_func` and `mbedtls_free_func` (`platform.c:44`, initialised to `MBEDTLS_PLATFORM_STD_CALLOC`). `mbedtls_calloc` and `mbedtls_free` at `platform.c:47-55` just dispatch through those pointers.

The index does not show the exact `#if` expression on `platform.c` lines 20–64. It only lists `MBEDTLS_PLATFORM_MEMORY`, `_CALLOC_MACRO` and `_FREE_MACRO` as gates. My reading is that the function-pointer layer is compiled in when `MBEDTLS_PLATFORM_MEMORY` is on and the two macros are not supplied. Confirm that against `platform.c` 18–22 and `platform.h` 136–170 before relying on it.

## What the library does with the facility

The library itself never calls `mbedtls_platform_set_calloc_free`. The index shows exactly one caller: `mbedtls_memory_buffer_alloc_init` (`library/memory_buffer_alloc.c:566-600`). That is the bundled fixed-buffer allocator, and it is the only in-library user of the hook.

`mbedtls_memory_buffer_alloc_init(buf, len)`:
- Zeroes its static `heap` context and, if `MBEDTLS_THREADING_C` is defined, initialises a mutex.
- Installs its own `buffer_alloc_calloc` / `buffer_alloc_free`, or the `_mutexed` wrappers when threading is on, via `mbedtls_platform_set_calloc_free`.
- Aligns `buf` to `MBEDTLS_MEMORY_ALIGN_MULTIPLE`, zeroes it, and writes the first block header with magic values.

Things to know about that design:
- **Silent failure on small buffers.** The function returns `void`. If `len` is below the minimum, it still installs the pointers before the length check and returns without initialising the heap. A caller cannot detect that from the return value.
- **Global state.** The heap is a single static context, so only one buffer allocator can be active per process.
- **Ownership contract.** Library APIs that allocate, such as `mbedtls_oid_from_numeric_string` ("must be freed by the caller using mbedtls_free()"), return memory that must go back through the same substituted free. A project that swaps `free` but frees library-allocated memory with libc `free` will corrupt its heap.

## Not verified

- The exact `#if` conditions in `platform.h` and `platform.c`.
- The `buffer_alloc_calloc` / `buffer_alloc_free` bodies, which would show the allocation policy.
- The `mbedtls_free_func` initialiser, which I did not query.