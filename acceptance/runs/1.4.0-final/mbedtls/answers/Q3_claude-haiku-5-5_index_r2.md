When mbedtls allocates memory, it calls its own `mbedtls_calloc()` and `mbedtls_free()`. Those are thin wrappers around two function pointers that default to "uninitialized" stubs, and the platform layer can be pointed at whatever allocator the project wants. The default build does not use `malloc` at all unless the integrator opts in.

**The call chain (runtime substitution, the default when `MBEDTLS_PLATFORM_MEMORY` is on)**

```
library code (e.g. ecp.c, cipher_wrap.c, asn1parse.c)
  └─ mbedtls_calloc(n, size)           library/platform.c:47
       └─ (*mbedtls_calloc_func)(n, size)   function pointer
            └─ whatever was registered via mbedtls_platform_set_calloc_free()
```

The pointers are declared at `library/platform.c:44-45`:

```c
static void * (*mbedtls_calloc_func)(size_t, size_t) = MBEDTLS_PLATFORM_STD_CALLOC;
static void (*mbedtls_free_func)(void *) = MBEDTLS_PLATFORM_STD_FREE;
```

If the integrator never sets `MBEDTLS_PLATFORM_STD_CALLOC`, the default is `platform_calloc_uninit`, which returns NULL. `MBEDTLS_PLATFORM_STD_FREE` defaults to a no-op. So an unconfigured build fails allocations rather than silently calling libc.

**How a project substitutes its allocator**

1. **Enable the layer.** Define `MBEDTLS_PLATFORM_MEMORY` in the user config. It is off by default (`include/mbedtls/mbedtls_config.h:208`). `MBEDTLS_PLATFORM_C` must also be on, which is the default.
2. **Pick a binding style:**
   - **Runtime (function pointers).** Leave `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` undefined. Call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` once before any other mbedtls call. The header declares it at `include/mbedtls/platform.h:160`.
   - **Compile time (macros).** Define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` (they must be set together). `platform.h:139-144` then `#define`s `mbedtls_calloc`/`mbedtls_free` directly to your functions. There is no indirection, and the runtime setter is compiled out (`platform.c:20-22`). The macros take precedence if both styles are configured.
3. **Or provide the standard names.** If you keep the runtime path but want a different default, define `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` to your functions. With `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` you must supply them, because the library otherwise won't reference libc `calloc`/`free`.
4. **Contract the allocator must meet** (from the config comments at `mbedtls_config.h:4113-4132`): calloc must zero the buffer; a NULL return is a legal failure; free must accept NULL; and free is only ever passed pointers that calloc returned.

If you use the macro path, `mbedtls_calloc` is an ordinary function name at the call site, so your replacement needs to be a drop-in for `calloc`'s signature.

**What the library does with the facility**

- **Every dynamic allocation goes through the wrapper.** The index shows about 147 call sites of `mbedtls_calloc`, including context constructors in `cipher_wrap.c` (AES, GCM, CCM, ChaCha20, and others), `pk_wrap.c` key allocation, `ecp.c` point multiplication, `asn1parse.c`, `lms.c`, and `dhm.c`. The library never calls libc `malloc`/`calloc` directly on these paths.
- **It does not call `mbedtls_platform_set_calloc_free` on its own.** The only in-library caller is `mbedtls_memory_buffer_alloc_init` (`library/memory_buffer_alloc.c:566-600`). That is the library's bundled allocator. It runs over a caller-supplied buffer, so the integrator gets a heap with no `malloc` dependency. It sets the allocator pointers to its own `buffer_alloc_calloc`/`buffer_alloc_free`. With `MBEDTLS_THREADING_C` it uses mutex-wrapped variants. Its header comment says this is the only way the library swaps the allocator itself.
- **The uninitialized-stub default is deliberate.** `platform.c:25-42` exists so that a build with `MBEDTLS_PLATFORM_MEMORY` but no allocator fails at runtime, not at link time. The `component_test_psa_crypto_without_heap` test script exercises the "core cannot allocate" configuration.

**Caveats**

- I did not read `buffer_alloc_calloc` or `mbedtls_memory_buffer_alloc_free` bodies, so I haven't verified how the bundled heap handles fragmentation or free-list reclamation.
- The index has no definition site for `MBEDTLS_PLATFORM_CALLOC_MACRO`/`FREE_MACRO` because they are commented out in the shipped config. That is expected. Their only definition is by the user.
- The 147 call-site count is from the index's caller tally, which I capped at 25 in the query. I didn't enumerate all of them.