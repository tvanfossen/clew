## What an allocation call resolves to

Library code calls `mbedtls_calloc()` / `mbedtls_free()`, never `calloc()` / `free()` directly. Two things decide what those names become, and the index shows the split:

```
ctx alloc in library (e.g. md.c ALLOC, cipher_wrap *_ctx_alloc)
  └─ mbedtls_calloc (macro, include/mbedtls/platform.h:167)
       ├─ MBEDTLS_PLATFORM_MEMORY off (shipped default) → calloc()   [direct libc]
       └─ MBEDTLS_PLATFORM_MEMORY on  → mbedtls_calloc() (library/platform.c:47)
             └─ (*mbedtls_calloc_func)(n, size)   ← runtime function pointer
```

- **Default build:** `MBEDTLS_PLATFORM_MEMORY` is off in `include/mbedtls/mbedtls_config.h:208`. The dispatch function `mbedtls_calloc` in `platform.c` is compiled only under that gate, so the macro goes straight to libc. Free is the same with `mbedtls_free` → `free()`.
- **Dispatch build:** `MBEDTLS_PLATFORM_MEMORY` on. `platform.c` holds two function pointers, `mbedtls_calloc_func` and `mbedtls_free_func`, and every call goes through them.

Two more macros can override the libc name in that dispatch path: `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`. The index has no definition site for either, so they are user-supplied names, off by default.

## Substituting an allocator

Two routes, both visible in the index:

1. **Compile-time:** define `MBEDTLS_PLATFORM_MEMORY` in the config, then either point `MBEDTLS_PLATFORM_STD_CALLOC` / `STD_FREE` at your functions or define the `_MACRO` pair. `tests/configs/user-config-malloc-0-null.h` does this: it sets `MBEDTLS_PLATFORM_MEMORY` and maps `MBEDTLS_PLATFORM_STD_CALLOC` to a `custom_calloc` function.
2. **Run-time:** call `mbedtls_platform_set_calloc_free(calloc_fn, free_fn)` (`library/platform.c:57`). It just stores the two pointers. It is the same hook the library's own allocator uses.

The default pointer depends on `MBEDTLS_PLATFORM_STD_CALLOC`. When it is off, `platform.c:32` installs `platform_calloc_uninit`, which always returns `NULL`. In that configuration every allocation fails until the integrator installs an allocator. I inferred this from the `#if` gating in the index rather than from the header text, so check `platform.c:20-40` before relying on it. I did not confirm the matching default for the free pointer.

## What the library does with the facility

- **Built-in heap:** `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566`) takes a caller buffer and carves it into blocks with magic-number headers. It then calls `mbedtls_platform_set_calloc_free` with its own `buffer_alloc_calloc` / `buffer_alloc_free`, or the `_mutexed` variants when `MBEDTLS_THREADING_C` is on. `buffer_alloc_calloc` (line 199) does a first-fit search of the free list, rejects overflowing `n * size`, aligns the request, and splits blocks. `mbedtls_memory_buffer_alloc_free` tears it down. The index shows `main` in `programs/test/selftest.c` as its only caller. It is not used on the library's normal paths.
- **Everywhere else:** the library's own call sites use only the `mbedtls_calloc` / `mbedtls_free` names. Examples are `mbedtls_md_setup`'s `ALLOC` macro (`library/md.c`), the `*_ctx_alloc` / `*_ctx_free` pairs in `cipher_wrap.c`, PSA key and buffer helpers, and the X.509 and SSL parsers. So one hook covers the whole library.
- **Zeroize-then-free:** `mbedtls_zeroize_and_free` (`library/platform_util.c:139`) wipes the buffer and then calls `mbedtls_free`. The library uses it for secret material such as bignums.

## Caveats

- The index reports no definition site for `MBEDTLS_PLATFORM_CALLOC_MACRO` or `FREE_MACRO`. Their names are not defined in the library, so a substitution through them depends on your own config.
- `mbedtls_zeroize_and_free` is listed with liveness `orphan`, even though 73 callers are unresolved. I didn't resolve that discrepancy.