**Short answer:** mbedtls never calls `calloc`/`free` directly. Every allocation goes through `mbedtls_calloc()` and `mbedtls_free()`, and what those resolve to depends on three configuration options. The library's own `mbedtls_memory_buffer_alloc` uses the same runtime hook to replace the allocator with a static heap.

**What gets called**

```
library code (~147 call sites, e.g. aes_ctx_alloc, ecp_mul_comb)
   │  mbedtls_calloc(n, size) / mbedtls_free(p)
   ▼
┌─ MBEDTLS_PLATFORM_MEMORY off ───────────────► calloc / free       (platform.h:163-168, macros)
├─ MBEDTLS_PLATFORM_MEMORY on,
│  CALLOC_MACRO + FREE_MACRO defined ─────────► your macros          (platform.h:139-145, no platform.c code emitted)
└─ MBEDTLS_PLATFORM_MEMORY on, macros absent:
      mbedtls_calloc() → mbedtls_calloc_func  (platform.c:47-50, static ptr at :44)
      mbedtls_free()   → mbedtls_free_func    (platform.c:52-55, static ptr at :45)
      initial value = MBEDTLS_PLATFORM_STD_CALLOC / _FREE
```

With `MBEDTLS_PLATFORM_MEMORY` off, the header maps `mbedtls_calloc` straight to `calloc` at compile time. With it on, the calls go through two static function pointers in `library/platform.c`. Those start at `MBEDTLS_PLATFORM_STD_CALLOC`/`_FREE`, which default to libc `calloc`/`free` when `MBEDTLS_PLATFORM_NO_STD_FUNCTIONS` is off. When that flag is on and no std functions are configured, the default is `platform_calloc_uninit` (returns NULL) and a no-op free (`platform.c:25-42`). So an unconfigured bare-metal build fails allocations cleanly instead of failing to link.

**How a project substitutes its allocator**

1. **Compile time (fastest, no runtime hook).** Enable `MBEDTLS_PLATFORM_MEMORY` and define *both* `MBEDTLS_PLATFORM_CALLOC_MACRO` and `MBEDTLS_PLATFORM_FREE_MACRO` in its `mbedtls_config.h` (or user config). The header then `#define`s `mbedtls_calloc`/`mbedtls_free` to your symbols, and `platform.c` omits its whole dispatch block (`platform.c:20-22`, `:64`). The two macros must be set together.
2. **Runtime.** Enable `MBEDTLS_PLATFORM_MEMORY` without the macros, then call `mbedtls_platform_set_calloc_free(my_calloc, my_free)` (`platform.c:57-63`) before any allocation. The setter is a plain pointer assignment with no locking, so it belongs in init code, not on a thread that is already running TLS.
3. **Swap the default target.** Define `MBEDTLS_PLATFORM_STD_CALLOC` and `MBEDTLS_PLATFORM_STD_FREE` to point the initial function pointers at your functions, and still use the runtime setter if you need to change them later.

The contract the config documents (`mbedtls_config.h:4113-4133`): calloc must zero the memory, `free(NULL)` must be a no-op, and a pointer passed to free must have come from the matching calloc. Calloc with a zero product may return NULL or a valid pointer.

The repo's own test config does this: `tests/configs/user-config-malloc-0-null.h` defines `custom_calloc` and related hooks. I did not open that file to check its exact configuration.

**What the library does with the facility itself**

- **Uniform use.** Every ctx alloc/free in `cipher_wrap.c`, `pk_wrap.c`, `asn1parse.c`, `ecp.c`, `lms.c`, `dhm.c`, `md.c`, and the SSL test helpers goes through the wrappers. A grep of `library/` shows no direct `calloc`/`malloc`/`free` calls. The one exception is `memory_buffer_alloc.c:404`, which frees `hdr->trace`, a backtrace buffer, under `MBEDTLS_MEMORY_BACKTRACE`. I did not trace how that buffer was allocated, so I can't say whether that free is symmetric with the allocation.
- **Built-in heap.** `mbedtls_memory_buffer_alloc_init(buf, len)` (`memory_buffer_alloc.c:566-600`) takes a caller-supplied buffer and calls `mbedtls_platform_set_calloc_free()` with its own `buffer_alloc_calloc_mutexed`/`buffer_alloc_free_mutexed` (or the non-mutexed pair if `MBEDTLS_THREADING_C` is off). From then on, every library allocation is served from that static buffer, and no libc heap is touched. The hooks are installed before the length check, so a too-small buffer still leaves the hooks replaced. I did not trace what allocation does in that state.
- **Process-global effect.** Because the hook is a process-wide pointer, calling `mbedtls_memory_buffer_alloc_init` in one component changes allocation for every mbedtls user in the process. The index shows no separate free/reset path for the hooks in what I read.

I checked the function bodies and the config documentation directly, and used the index for callers and gating. I did not build or run anything.