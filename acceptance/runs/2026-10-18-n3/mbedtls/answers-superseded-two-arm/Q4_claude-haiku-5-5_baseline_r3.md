**Negative return to string**

1. **Caller invokes `mbedtls_strerror(ret, buf, buflen)`**, defined in `library/error.c`. That file is generated; the source is `scripts/data_files/error.fmt`, with placeholders filled in by `scripts/generate_errors.pl`.
2. **Sign is dropped.** `ret` is negated, so `-0x0001` becomes `0x0001`.
3. **The code is split by bitmask.** Error codes are a high-level module part (`ret & 0xFF80`) plus a low-level part (`ret & ~0xFF80`), per the comment in `error.h` ("Module dependent error code, 5 bits").
4. **High-level lookup.** `mbedtls_high_level_strerr()` switches on the high part (e.g. `MBEDTLS_ERR_SSL_*`, `X509_*`, `PK_*`). If it finds nothing, the buffer gets `UNKNOWN ERROR CODE (XXXX)`.
5. **Fatal-alert short circuit.** When the high part is `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE` and TLS is enabled, the function returns without decoding the low part.
6. **Low-level lookup.** The low part is decoded via `mbedtls_low_level_strerr()`. If both parts exist, they are joined as `"HIGH : LOW"`, e.g. `"SSL - ... : X509 - ..."`. Unknown low codes give `UNKNOWN ERROR CODE`.
7. **Zero low part** means the high-level string stands alone; a zero code produces an empty buffer.

Each generated `case` has the form `case -(MBEDTLS_ERR_FOO): return "MODULE - description";`. The `MODULE` prefix comes from the macro name, e.g. `MBEDTLS_ERR_X509_...` → `X509`.

**Adding a new error code**

1. **Define it in a public header** under `include/mbedtls/` as `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....`. The value must be negative and unique across all headers.
2. **Add a Doxygen description** in exactly one place: either a `/** ... */` comment before the define, or a `/**< ... */` after it. The generator dies if both or neither are present. A `\name` block directly before a define is ignored, per `generate_errors.pl:76`.
3. **Make sure the module is known to the generator.** `scripts/generate_errors.pl` (lines 36–43) hard-codes `@low_level_modules` and `@high_level_modules`. A new module name must be added there, or the generator exits with `Do not know how to handle`. The `$define_name` and `$include_name` special cases (lines 118–133) also need updating if the module's config macro or header name doesn't follow the default pattern.
4. **Include the header.** The generator emits `#include "mbedtls/<module>.h"` guarded by the module's `MBEDTLS_<X>_C` macros. If a header defines codes but isn't in the include list, the generator errors out.
5. **Regenerate `library/error.c`.** It's a Makefile target (`library/Makefile:355–360`), or run `perl scripts/generate_errors.pl` from the repo root. `library/error.c` is tracked in git, so commit the regenerated file along with the header change.
6. **Add a test.** `tests/suites/test_suite_error.data` drives `test_suite_error.function`, which calls `mbedtls_strerror` and checks the string.

**Caveat:** I read the generator and the runtime decoder but did not run `generate_errors.pl` or the error test suite here, so I haven't confirmed that the committed `library/error.c` matches current generator output. Running the generator and diffing would settle that.