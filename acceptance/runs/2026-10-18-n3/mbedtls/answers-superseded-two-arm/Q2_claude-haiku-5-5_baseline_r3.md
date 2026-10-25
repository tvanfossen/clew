**What it does.** `include/mbedtls/private_access.h` defines the macro:

```c
#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
#define MBEDTLS_PRIVATE(member) private_##member
#else
#define MBEDTLS_PRIVATE(member) member
#endif
```

So a field like `mbedtls_ssl_context`'s `MBEDTLS_PRIVATE(state)` is spelled `private_state` for normal users, and any code touching it fails to compile. The struct layout is unchanged; only the name changes. The point is to stop applications from depending on internals the project may reorganize in a minor release. `ssl.h:5163` marks direct access as deprecated, and `docs/3.0-migration-guide.md:74` describes `bar.MBEDTLS_PRIVATE(foo)` as a last resort "at your own risk". It is a deterrent, not a security boundary: any application can define `MBEDTLS_ALLOW_PRIVATE_ACCESS` itself.

**Who it's for.** The intended audience is external application code. The public API is the supported surface; the members are hidden so callers use accessors instead. `ChangeLog` shows accessors being added for exactly this reason (around lines 756–801).

**Where the opt-out is turned on in this tree:**

| Location | How it's enabled | Effect |
|---|---|---|
| `library/common.h:132` | Unconditional `#define MBEDTLS_ALLOW_PRIVATE_ACCESS` | Every library `.c` that includes `common.h` gets direct member access. 107 of the 109 `library/*.c` files do this (the two that don't, `ecp_curves_new.c` and `ssl_debug_helpers_generated.c`, don't use `MBEDTLS_PRIVATE` at all). |
| `tests/suites/test_suite_common.function:2`, `tests/src/certs.c`, and other test suites | They `#include "common.h"` (x509write reaches it through `x509_internal.h`) | Test suites compile as library-internal code and can reach private fields. |
| `programs/ssl/ssl_server2.c:8`, `programs/ssl/ssl_client2.c:8` | Explicit `#define` before `#include "ssl_test_lib.h"` | These sample/test programs can read and write internal state. |

**What this means for those places.**

- **Library code:** `MBEDTLS_PRIVATE(x)` is effectively a no-op there, so internal structs can change freely. Library and tests are built together, so there is no external ABI to protect.
- **Test suites:** they can assert on internal state, which means a refactor of private fields can break tests even when the public API is unchanged. That is intended.
- **Test programs (`ssl_server2`, `ssl_client2`):** they are in-tree tools, not supported applications, so they're coupled to the exact library version they ship with.
- **Ordering matters.** The `#ifndef` is evaluated when `private_access.h` is first included, and the header guard stops it being re-evaluated. The opt-in must come before any mbedtls header in the translation unit. The library files and the two programs all put it first (`common.h` at the top of `ssl_tls.c`, the define at line 8 of the programs). An application that defines the macro after including mbedtls headers gets the private names silently.

I didn't check the `programs/fuzz/*.c` files individually; I only confirmed that they're in the list of files referencing the macro or `MBEDTLS_PRIVATE`.