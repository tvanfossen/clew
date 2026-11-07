The string comes from `mbedtls_strerror()` in `library/error.c`, a file the build generates from the public headers. The caller passes the return value and a buffer:

```c
char buf[128];
mbedtls_strerror(ret, buf, sizeof(buf));
```

Here is the path, using the example `-0x40A0`:

1. **Sign is dropped.** `mbedtls_strerror` negates `ret` if it is negative, so the code is treated as positive `0x40A0`.
2. **High-level part.** The mask `0xFF80` selects the module bits. `mbedtls_high_level_strerr()` switches on that value against `case -(MBEDTLS_ERR_RSA_...)` entries and returns something like `"RSA - Bad input parameters to function"`. No match gives `UNKNOWN ERROR CODE (xxxx)`.
3. **Early exit for fatal SSL alerts.** If the high-level value is `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE` and `MBEDTLS_SSL_TLS_C` is enabled, the function returns without decoding the low bits.
4. **Low-level part.** `ret & ~0xFF80` gives the remainder, here `0x0020`. If it is nonzero, `mbedtls_low_level_strerr()` looks it up and returns something like `"AES - Invalid key length"`. The two parts are joined with `" : "`, giving `"RSA - Bad input parameters to function : AES - Invalid key length"`. This pairing is pinned in `tests/suites/test_suite_error.data`.

The lookup tables are not hand-written. `scripts/generate_errors.pl` scans every `include/mbedtls/*.h` for `#define MBEDTLS_ERR_xxx -0x....` lines. It takes the description from a Doxygen comment that sits either before or after the define (not both, and not neither). It then emits one `case` per code into `library/error.c`, using `scripts/data_files/error.fmt` as the template. The generated file is committed, and `tests/scripts/check-generated-files.sh` fails if it is out of date.

**To add a new error code:**

1. **Define it in the module's public header.** Use the negative hex form with a value that is not already taken. Put a `/** ... */` or `/**< ... */` description on the define. The generator dies on duplicate values or on a missing or doubly-specified description.
2. **Pick the right range.** Low-level codes fall in `0x0001–0x007F`. High-level codes are module-level values in the `0x xx00` range, so new codes should go in the module's existing block. Check the grouping comments in the header.
3. **If the module is new, register it.** The module name derived from `MBEDTLS_ERR_<MODULE>_` must appear in `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`, or the script exits with `Do not know how to handle`. Also make sure the header name matches the module (lowercased, with `NET` → `net_sockets`) and is included by the generator's `#include` block.
4. **Regenerate.** Run it through the build (`make` in `library/` or the CMake target), or run `scripts/generate_errors.pl` directly from the repo root. Commit the regenerated `library/error.c` alongside the header change.
5. **Add a test.** Add a line to `tests/suites/test_suite_error.data` (`error_strerror:-0x....:"Module - description"`). Run it red first, as the repo's test rules require.

One caveat: the high-level and low-level tables are split by mask arithmetic, not by module name. A code whose value does not fit the module's `0xFF80`-aligned block will decode to `UNKNOWN ERROR CODE`, and the generator will not warn you about that. Check the value by hand against its neighbours.