**Short answer:** `mbedtls_strerror()` splits the code into a high-level part and a low-level part, looks each part up in a `switch` table, and joins the strings. Nobody maintains those tables by hand. `scripts/generate_errors.pl` builds `library/error.c` from the `#define`s in `include/mbedtls/*.h`. So adding a string means adding a documented `#define` and regenerating.

## Runtime path

```
ret = -0x4080 (say)
  │
  ├─ mbedtls_strerror(ret, buf, buflen)        library/error.c:792
  │    ├─ buflen==0 → return; memset buf to 0
  │    ├─ ret = -ret                           (sign dropped)
  │    │
  │    ├─ if (ret & 0xFF80)                    high-level bits present?
  │    │    └─ mbedtls_high_level_strerr(ret)  switch on (ret & 0xFF80)
  │    │         → "RSA - Bad input parameters to function"  (or "UNKNOWN ERROR CODE (XXXX)")
  │    │         └─ if high == MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE → return early
  │    │
  │    ├─ low = ret & ~0xFF80; if 0 → done
  │    ├─ if high already written → append " : "
  │    └─ mbedtls_low_level_strerr(ret)      switch on (ret & ~0xFF80)
  │         → e.g. "AES - Invalid key length"  (or "UNKNOWN ERROR CODE (XXXX)")
  │
  └─ buf = "RSA - Bad input parameters to function"
```

- **Bit split.** The 0xFF80 mask selects the high-level module (bits 7–15). The low 7 bits (`0x007F`) are the low-level module. `include/mbedtls/error.h` documents the layout in a long comment.
- **Sign.** Both `mbedtls_*_strerr` and `mbedtls_strerror` negate first. The generated cases are `case -(MBEDTLS_ERR_X):`, so the tables match the positive value.
- **Combined codes.** A single return can carry both parts, for example an SSL code plus a low-level cause. The output is `"HIGH : LOW"`.
- **Unknown codes.** If a code's bits are not in the table, the output is `UNKNOWN ERROR CODE (%04X)`, not an empty string.
- **Fatal alerts.** `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE` returns after the high-level part. The low part is the peer's alert, not a library error.
- **Disabled module.** If `MBEDTLS_ERROR_C` is off, `mbedtls_strerror` writes an empty string. Each table case is also wrapped in its module's `#if defined(MBEDTLS_X_C)`.

The public functions are `mbedtls_strerror`, `mbedtls_high_level_strerr` and `mbedtls_low_level_strerr`, declared in `include/mbedtls/error.h`.

## Adding a new error code

1. **Define it in the module header.** Put `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....` in `include/mbedtls/<module>.h`. Pick an unused value in that module's range, using the layout table in `error.h`. Duplicate values fail the generator (`Duplicated error code`).
2. **Document it, exactly once.** Give it either a `/** ... */` comment before the define or a `/*!< ... */` comment after it. Having neither, or both, fails the generator. The text becomes the string.
3. **Check the module is known.** The module token is the word after `MBEDTLS_ERR_`. It must appear in `@low_level_modules` or `@high_level_modules` in `generate_errors.pl`, or the script exits with `Do not know how to handle`. A brand-new module also needs its `#if` guard name and include name set in the script.
4. **Regenerate, don't hand-edit.** Run the normal build (`make` in `library/`, or the CMake target), which calls `generate_errors.pl`. Do not edit `library/error.c` directly. CI runs `tests/scripts/check-generated-files.sh`, which regenerates it and diffs the result.
5. **Add a test first.** In `tests/suites/test_suite_error.data`, add a line like `error_strerror:-0x....:"MODULE - description"`. The string must match what the generator produced. Run the test red before the change, then green.
6. **Changelog.** If the new string is user-visible, which it normally is, add an entry under `ChangeLog.d/` as described in `ChangeLog.d/00README.md`.

I read the generator, the header, `error.c` and the test suite. I did not build the library or run the tests, so the regeneration and test steps above are from the scripts, not a run.