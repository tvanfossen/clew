**How a code becomes a string**

1. **Source of truth is the headers.** Each error is a `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....` in `include/mbedtls/*.h`, with a Doxygen description either before it (`/** ... */`) or after it (`/*!< ... */`). Examples: `include/mbedtls/error.h:98` (`MBEDTLS_ERR_ERROR_GENERIC_ERROR -0x0001`) and `tests/suites/test_suite_error.data`.

2. **Generation, not hand-written.** `scripts/generate_errors.pl` scans the headers with a regex, rejects duplicate values, and builds two `switch` blocks. It writes them into `library/error.c` using the template `scripts/data_files/error.fmt`. Each case looks like `case -(MBEDTLS_ERR_RSA_BAD_INPUT_DATA): return "RSA - Bad input parameters to function";`. The module prefix comes from the macro name, and the text comes from the Doxygen description. The generator also emits the `#include "mbedtls/<module>.h"` lines and wraps each case in `#if defined(MBEDTLS_<MODULE>_C)`. The build runs it (`library/Makefile:355`, `library/CMakeLists.txt:139`), and `tests/scripts/check-generated-files.sh:135` fails CI if the checked-in `library/error.c` is stale.

3. **Runtime lookup.** `mbedtls_strerror()` in `library/error.c` (generated) does this:
   - Takes the absolute value, since codes are negative.
   - Splits the code by bit mask. Bits `0xFF80` are the high-level module (for example RSA, SSL, X509). Bits `~0xFF80` are the low-level module (for example AES, ASN1, BASE64).
   - Looks up the high part with `mbedtls_high_level_strerr()`, then the low part with `mbedtls_low_level_strerr()`.
   - Joins the two with `" : "`. Unknown parts become `UNKNOWN ERROR CODE (XXXX)`.
   - Stops early for `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`, since the low bits there are an alert code, not an error.
   - Writes into the caller's buffer, always NUL-terminated.

```
ret = -0x40A0
  -> |ret| = 0x40A0
  -> high = 0x4080 -> "RSA - Bad input parameters to function"
  -> low  = 0x0020 -> "AES - Invalid key length"
  -> "RSA - Bad input parameters to function : AES - Invalid key length"
```

If `MBEDTLS_ERROR_C` is off, `mbedtls_strerror()` returns an empty string (`library/error.c`, the `#else` branch).

**Adding a new error code**

1. Add the `#define` to the right header in `include/mbedtls/`, as `-0x....`. Pick an unused value in that module's range. The name must start with `MBEDTLS_ERR_<MODULE>_`.
2. Give it exactly one description: a Doxygen comment before it or `/*!<` after it, not both. Otherwise the generator dies. The text becomes the user-visible string, so write it as the message you want printed.
3. If the module is new, add its name to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`. Otherwise it exits with "Do not know how to handle". Also add a mapping there if the header or define name doesn't follow the default pattern.
4. Regenerate `library/error.c` (`make` in `library/`, or the CMake target), then commit it. CI's generated-file check will reject a stale file.
5. Add a case to `tests/suites/test_suite_error.data` with `depends_on` for the module, and run the error test suite through the project's test tooling.

I didn't run the generator or the tests. This is from reading the scripts and the code.