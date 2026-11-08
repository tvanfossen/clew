A negative return code becomes a string in three steps: a fixed bit split, two lookup switches, and a generated `error.c`. The strings are not written by hand. A generator builds them from the `MBEDTLS_ERR_*` defines in the headers.

**Runtime path**

1. The caller passes the code to `mbedtls_strerror(ret, buf, buflen)` (`library/error.c:792`). It zeroes the buffer, then negates the value, since codes are stored as negatives.
2. The code is split on bit masks. Bits `0xFF80` are the high-level module part, and the low 7 bits (`~0xFF80`) are the low-level part.
3. The high-level part goes to `mbedtls_high_level_strerr()`, and the low-level part goes to `mbedtls_low_level_strerr()` (`error.c:537`). Each is a `switch` over `case -(MBEDTLS_ERR_X): return "MODULE - description";`. Both return `NULL` on no match.
4. The two strings are joined with `" : "`, as in `"RSA - Bad input parameters to function : AES - Invalid key length"`. Either side that fails to match becomes `UNKNOWN ERROR CODE (XXXX)`.
5. Special case: if the high-level part is `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`, the function returns early and skips the low-level part.
6. If `MBEDTLS_ERROR_C` is off, a dummy version at `error.c:867` just writes an empty string.

**Where `error.c` comes from**

`library/error.c` is generated, not hand-written. The generator is `scripts/generate_errors.pl`, and its template is `scripts/data_files/error.fmt`. The generator:

- scans `include/mbedtls/*.h` for `#define MBEDTLS_ERR_\w+ -0x...`
- requires exactly one doc comment on each define, either before it or as a `/*!<` after-comment, and rejects a define with both or neither
- rejects duplicate values
- takes the module name from the middle of the define name (`MBEDTLS_ERR_<MODULE>_...`), then sorts it into the low-level or high-level list
- writes one `case` per code into the template placeholders

`tests/scripts/check-generated-files.sh:135` re-runs the generator and fails if `library/error.c` differs, so a hand edit to `error.c` is caught.

**To add a new error code**

1. Add the define in the module's header under `include/mbedtls/`, with a one-line doc comment before it or as a `/*!<` after-comment, not both:
   `#define MBEDTLS_ERR_FOO_BAR_BAZ -0x00XX`
   Pick a value that does not collide with an existing one. The generator dies on duplicates.
2. If the module is new, add it to the `@low_level_modules` or `@high_level_modules` list in `scripts/generate_errors.pl`. Otherwise the generator exits with "Do not know how to handle". Also add any header or `#if` mapping the generator needs.
3. Regenerate from the repo root with `scripts/generate_errors.pl`, which writes `library/error.c`. Do not edit `error.c` directly.
4. Add a case to `tests/suites/test_suite_error.data` using the `error_strerror:` format. Include the expected string, for example `"FOO - <description>"`. Add `depends_on:` for the module's `MBEDTLS_*_C` define. The test runs through `error_strerror` in `tests/suites/test_suite_error.function`.
5. Run the generated-files check and the error test suite. For the repo's gates, use its own test scripts; I did not run them here.

I did not build or run anything. The line numbers and the generator logic above come from reading the source and the index.