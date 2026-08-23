## What actually gets called

`mbedtls_calloc()` is not a direct call to libc — it's a thin indirection through a function pointer:

```c
// library/platform.c:44
static void * (*mbedtls_calloc_func)(size_t, size_t) = MBEDTLS_PLATFORM_STD_CALLOC;

// library/platform.c:47-50
void *mbedtls_calloc(size_t nmemb, size_t size)
{
    return (*mbedtls_calloc_func)(nmemb, size);
}
```

`mbedtls_free()` follows the identical pattern with a paired `mbedtls_free_func` pointer. By default `MBEDTLS_PLATFORM_STD_CALLOC` resolves to plain libc `calloc` (the index has no definition site for that macro to confirm the exact default text — it's a preprocessor default in `platform.h`/`platform_util.h`, and the index flags this rather than guessing), so out of the box `mbedtls_calloc`/`mbedtls_free` just wrap standard `calloc`/`free`.

There's a second layer worth knowing: `mbedtls_calloc` in application/library code is itself a **macro** (`include/mbedtls/platform.h:144`), gated by `MBEDTLS_PLATFORM_MEMORY` and `MBEDTLS_PLATFORM_CALLOC_MACRO`/`_FREE_MACRO`. If those aren't both defined, the macro just expands to the function described above. If a project defines `MBEDTLS_PLATFORM_CALLOC_MACRO`, every `mbedtls_calloc()` call site in the source is preprocessed straight to that macro — bypassing the function-pointer indirection entirely, at compile time rather than runtime.

## How a project substitutes its own allocator

Two independent substitution mechanisms exist, and they don't compose the same way:

1. **Runtime substitution (default path):** call `mbedtls_platform_set_calloc_free(calloc_func, free_func)`, which does exactly this:
   ```c
   int mbedtls_platform_set_calloc_free(void *(*calloc_func)(size_t, size_t),
                                        void (*free_func)(void *))
   {
       mbedtls_calloc_func = calloc_func;
       mbedtls_free_func = free_func;
       return 0;
   }
   ```
   This reassigns the global function pointers, so every subsequent `mbedtls_calloc`/`mbedtls_free` call in the library (dozens of call sites across ASN.1, PK, X.509, SSL, PSA, cipher contexts, etc.) transparently routes through the new allocator, no rebuild required.

2. **Compile-time substitution:** define `MBEDTLS_PLATFORM_MEMORY` plus `MBEDTLS_PLATFORM_CALLOC_MACRO`/`MBEDTLS_PLATFORM_FREE_MACRO` in `mbedtls_config.h` to point at project-specific symbols. This is the mechanism the `MBEDTLS_PLATFORM_MEMORY` config gate exists for (declared as a real config flag in `include/mbedtls/mbedtls_config.h:3297`, and there's a dedicated test config `tests/configs/user-config-malloc-0-null.h` exercising it) — used for constrained targets where you don't want the pointer-indirection overhead or want the allocator resolved statically.

## What the library itself does with this facility

mbedtls ships its own consumer of the runtime hook: `mbedtls_memory_buffer_alloc_init()` (in `include/mbedtls/memory_buffer_alloc.h`, implemented for the stack-based allocator). Per its documented brief, it does memory management inside a caller-supplied static buffer instead of calling `calloc()`/`free()`, and it wires itself in by calling `mbedtls_platform_set_calloc_free()` with its own two functions — turning the global `mbedtls_calloc`/`mbedtls_free` into pointers at that fixed buffer. This is the library's dogfooding of the substitution mechanism: it's meant for heap-less/embedded builds, and it explicitly notes that its own calloc/free are thread-safe only if `MBEDTLS_THREADING_C` is also enabled.

So the layering is: every allocation in the library funnels through `mbedtls_calloc`/`mbedtls_free` → a pair of global function pointers → either libc by default, a project's own allocator via `mbedtls_platform_set_calloc_free`, or mbedtls's own bundled static-buffer allocator via `mbedtls_memory_buffer_alloc_init`, with a separate compile-time macro path available for cases where even the pointer indirection isn't wanted.
