**Short answer:** every allocation inside the library goes through `mbedtls_calloc()` and `mbedtls_free()`. Those two functions are thin trampolines to function pointers that a project can replace at runtime, or replace at compile time with macros.

**What gets called**

1. Library code calls `mbedtls_calloc(n, size)` and `mbedtls_free(p)`. The index shows callers across ASN.1, X.509, SSL, PSA, bignum, the cipher context constructors and more.
2. In the default runtime-substitution build, `library/platform.c:47-55` forwards each call through a static pointer:
   ```c
   static void * (*mbedtls_calloc_func)(size_t, size_t) = MBEDTLS_PLATFORM_STD_CALLOC;
   static void (*mbedtls_free_func)(void *)            = MBEDTLS_PLATFORM_STD_FREE;
   void *mbedtls_calloc(size_t nmemb, size_t size) { return (*mbedtls_calloc_func)(nmemb, size); }
   ```
3. The pointers start at `MBEDTLS_PLATFORM_STD_CALLOC` / `MBEDTLS_PLATFORM_STD_FREE`. If those are not defined, `platform.c:24-42` substitutes `platform_calloc_uninit` (returns NULL) and `platform_free_uninit` (no-op). So a build with no allocator fails every allocation cleanly instead of linking to `calloc`.

**How a project substitutes its allocator**

There are two routes, and the header makes the compile-time one win when both are present.

- **Runtime (the normal route):** keep `MBEDTLS_PLATFORM_MEMORY` on, leave the `*_MACRO` options undefined, and call
  ```c
  mbedtls_platform_set_calloc_free(my_calloc, my_free);
  ```
  before the library allocates anything. This is `library/platform.c:57-63`, which just assigns the two globals. It has no locking, so call it before any threads start.
- **Compile time:** define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in your user config. `include/mbedtls/platform.h:139-144` then `#define`s `mbedtls_calloc` and `mbedtls_free` directly to your functions. `platform.c` drops its runtime code entirely (guard at `platform.c:20-22`), and `mbedtls_platform_set_calloc_free` no longer exists to call. Use this when you want no indirection, or when the allocator must be fixed at link time.
- Without `MBEDTLS_PLATFORM_MEMORY` at all, `platform.h:163-167` maps the names straight to libc `calloc`/`free`.

`mbedtls_config.h:4113-4151` states the contract: the allocator must zero the buffer, `free(NULL)` must be a no-op, and a non-null pointer passed to free must be one the allocator returned and that has not already been freed.

**What the library does with the facility itself**

- **Built-in heap:** `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566-600`) is a self-substitution. It carves allocations out of a caller-supplied buffer, and it calls `mbedtls_platform_set_calloc_free(...)` to install its own `buffer_alloc_calloc` or, when `MBEDTLS_THREADING_C` is on, `buffer_alloc_calloc_mutexed`. The header comment says it never calls libc `calloc`/`free`. This gives a static-memory system without touching the rest of the library.
- **Self-test:** `calloc_self_test` in `programs/test/selftest.c` exercises the hook.
- **Zeroize-then-free:** `mbedtls_zeroize_and_free` (`library/platform_util.c:139-146`) wipes the buffer and then calls `mbedtls_free`, so secrets released through it also go through the substituted free.

**Caveats**

- I did not verify the shipped default of `MBEDTLS_PLATFORM_MEMORY` or whether `MBEDTLS_MEMORY_BUFFER_ALLOC_C` is enabled in the default config. Check `mbedtls_config.h` before relying on either.
- The index reports `mbedtls_zeroize_and_free` as orphaned in the AST, but its doxygen-sourced callers number 73. Trust the doxygen figure for who calls it.