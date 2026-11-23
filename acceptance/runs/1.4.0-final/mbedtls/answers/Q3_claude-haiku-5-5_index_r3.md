**Short answer:** every allocation in the library goes through `mbedtls_calloc()` and `mbedtls_free()`, never directly through libc. By default those two names are compile-time aliases for `calloc` and `free`. A project can replace them at compile time with macros, or at runtime with a function-pointer hook. The library's own memory-buffer allocator uses that same runtime hook.

**What gets called**

```
library code (~147 call sites via mbedtls_calloc)
        │
        ▼
mbedtls_calloc()  ── library/platform.c:47 ──► (*mbedtls_calloc_func)  ──► calloc / your fn
```

- **Default build (`MBEDTLS_PLATFORM_MEMORY` off, the shipped default):** `include/mbedtls/platform.h:166-167` defines `mbedtls_calloc` as `calloc` and `mbedtls_free` as `free`. The call is libc `calloc`, resolved at compile time. The `platform.c` hook code is compiled out.
- **Compile-time substitution:** define both `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO`. `platform.h:139-144` then maps `mbedtls_calloc`/`mbedtls_free` to your macros, and `platform.c:20-22` omits its runtime code. You must define both or neither (`mbedtls_config.h:4149-4151`).
- **Runtime substitution:** define `MBEDTLS_PLATFORM_MEMORY` without the two macros. `platform.h:148-161` declares the functions. `platform.c:44-45` holds two function pointers, initialised to `MBEDTLS_PLATFORM_STD_CALLOC`/`_FREE`. Then call the setter before any allocation:

  ```c
  mbedtls_platform_set_calloc_free(my_calloc, my_free);
  ```

  The setter (`platform.c:57-63`) just assigns the two pointers and returns 0. It does no locking and does not check for prior use. If `MBEDTLS_PLATFORM_STD_CALLOC` is undefined, the default is a stub that returns NULL, so allocation fails until you set a function (`mbedtls_config.h:4113-4134`).

- **Contract your allocator must meet** (`mbedtls_config.h:4113-4134`): `calloc` must zero the memory; a zero-size request may return NULL or a valid pointer; `free(NULL)` must be a no-op; and `free` must only receive pointers from your `calloc`.

**What the library does with the facility**

1. **Routes every allocation through the hook.** A grep of `library/` finds no direct `calloc(` or `free(` calls, apart from the backtrace case below. Callers include the cipher context constructors in `cipher_wrap.c`, `asn1parse.c`, the ECP comb code, the PK-to-PSA import paths, and `dhm.c`'s file loader.
2. **Ships its own allocator on top of the hook.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`library/memory_buffer_alloc.c:566-600`) manages a caller-supplied static buffer and installs its own `calloc`/`free` through `mbedtls_platform_set_calloc_free`. With `MBEDTLS_THREADING_C` it installs mutex-wrapped variants. The programs `ssl_server2`, `ssl_client2`, `ssl_pthread_server` and `benchmark` use it this way.
3. **Its one direct libc `free`** (`memory_buffer_alloc.c:404`) is under `MBEDTLS_MEMORY_BACKTRACE` and frees the result of `backtrace_symbols()` (lines 282, 348). That pairing is correct, so it is not a bypass.

**Caveats for a substituting project**

- The hook is process-global, not per-context. Setting it replaces the allocator for every mbedtls user in the process, and `memory_buffer_alloc_init` silently overwrites any earlier setting.
- Call the setter before any library use. Allocations made earlier stay with the old allocator, so freeing them with the new `free` is undefined behaviour.
- The default `MBEDTLS_PLATFORM_STD_*` values are only meaningful when the platform hook is compiled in. A build with `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` and no replacement fails every allocation at runtime.
- The repo's `component_test_psa_crypto_without_heap` (`tests/scripts/components-configuration-crypto.sh`) builds a configuration where the core library cannot call calloc/free while test code can. I read only its description, not the script body.

I did not build or run anything; the answers above come from the index and from reading the cited source lines.