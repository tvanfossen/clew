The string comes from a generated file, `library/error.c`, which is produced from `scripts/generate_errors.pl` and `scripts/data_files/error.fmt`. The `#define`s in the public headers are the source of truth.

**Runtime path, using `-0x40A0` (RSA bad input + AES invalid key length) as the example**

```
mbedtls_strerror(ret, buf, buflen)            library/error.c (generated)
  ret = -ret                                  -> 0x40A0
  if (ret & 0xFF80)                           high part present
     mbedtls_high_level_strerr(ret)           -> "RSA - Bad input parameters to function"
  low = ret & ~0xFF80                         -> 0x0020
  if (low)
     append " : "                             (only if a high part was written)
     mbedtls_low_level_strerr(ret)            -> "AES - Invalid key length"
  result: "RSA - Bad input parameters to function : AES - Invalid key length"
```

1. The caller gets a negative `int`. `mbedtls_strerror()` takes the absolute value first.
2. The bits above `0xFF80` are the high-level code, one module per code range. `mbedtls_high_level_strerr()` switches on that masked value, and each `case` is `-(MBEDTLS_ERR_xxx)`, so the lookup matches the positive magnitude.
3. The bits under `0x80` are the low-level code (AES, SHA, ERROR, and so on). `mbedtls_low_level_strerr()` does the same lookup for them.
4. The two halves are joined with `" : "`. If a code isn't in the table, the output is `UNKNOWN ERROR CODE (XXXX)` for that half. A fatal SSL alert (`MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`) returns early after the high-level part, so its low bits are not translated.
5. `mbedtls_strerror()` always zeroes the buffer first, and it returns with an empty string when `buflen == 0`.

The `#if defined(MBEDTLS_xxx_C)` guards in the generated file mean a module's strings only exist when that module is built. When `MBEDTLS_ERROR_C` is off, `mbedtls_strerror()` is a stub that writes an empty string.

**Adding a new error code**

1. **Define the code** in the module's header, `include/mbedtls/<module>.h`, as a negative hex value with a Doxygen description. The description can go before the define (`/** ... */`) or after it (`/*!< ... */`), but not both, and it must not be missing. The generator aborts otherwise. Values must be unique across the library; a duplicate aborts too.
2. **Check the module is registered** in `scripts/generate_errors.pl`. Low-level modules go in `@low_level_modules` and high-level ones in `@high_level_modules`. An unlisted module makes the generator exit with `Do not know how to handle`. A new module also needs its `#if` guard mapping and its header included, or the generator reports `has not been included`.
3. **Regenerate `library/error.c`.** The Makefile rule runs the generator when headers change, and CMake does the same. `library/error.c` is committed to git, so the regenerated file has to be committed too. Otherwise the shipped strings won't match the headers.
4. **Add a test row** to `tests/suites/test_suite_error.data`, using the `error_strerror:<code>:"<expected>"` format with the right `depends_on:` line. Per the repo's rules, write the test first and watch it fail.

Two things I noticed while reading the generator. First, it escapes backslashes in descriptions but not double quotes, so a `"` in a description would break the generated C string literal. Second, I did not check that the committed `library/error.c` currently matches the generator output. I also did not run the generator or the test suite, so those two points are from reading the code, not from a build.