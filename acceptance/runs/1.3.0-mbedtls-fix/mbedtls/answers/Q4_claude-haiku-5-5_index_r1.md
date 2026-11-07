A negative code becomes a string in three layers: a runtime lookup in `library/error.c`, a generated switch table, and a Perl script that builds that table from the public headers. To add one, you edit the header and regenerate the committed `library/error.c`.

**Runtime path**

```
caller: mbedtls_strerror(ret, buf, buflen)            library/error.c:792
  ├─ buflen == 0 → return; else memset(buf, 0)
  ├─ ret = -ret if negative (positive input also works)
  ├─ high = ret & 0xFF80 → mbedtls_high_level_strerr(ret)   :174
  │     NULL → "UNKNOWN ERROR CODE (%04X)"
  │     SSL fatal alert (-MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE) → return, skip low level
  ├─ low = ret & ~0xFF80; low == 0 → return
  ├─ if high already written: append " : " and shift buf
  └─ mbedtls_low_level_strerr(ret)                   :537
        NULL → "UNKNOWN ERROR CODE (%04X)"
```

Each lookup is a `switch` on the masked value. The `case` labels and strings are generated, so nothing hand-written holds the mapping. An example result is `-0x40A0` → `"RSA - Bad input parameters to function : AES - Invalid key length"`, from the test data.

If `MBEDTLS_ERROR_C` is off, the `#else` branch writes an empty string. The `MBEDTLS_ERROR_STRERROR_DUMMY` gate keeps the code compiled but still returns no text.

**How the table gets generated**

- `library/CMakeLists.txt:133-145` runs `perl scripts/generate_errors.pl include/mbedtls scripts/data_files library/error.c` whenever any `include/mbedtls/*.h` changes.
- The script scans every header with a regex for `#define MBEDTLS_ERR_<X> -0x....` plus its Doxygen description. The description is either a `/** */` comment before it or a `/*!< */` comment after it. Having both, or neither, is a fatal error.
- `scripts/data_files/error.fmt` is the template. The script fills `HEADER_INCLUDED`, `LOW_LEVEL_CODE_CHECKS` and `HIGH_LEVEL_CODE_CHECKS` into it.
- The module prefix (the `X` in `MBEDTLS_ERR_X_`) decides high versus low level, using the two lists at the top of `generate_errors.pl`. It also sets the `#if defined(MBEDTLS_X_C)` guard and the header to include.

**What a contributor has to do to add one**

1. **Add the define** in the module's header under `include/mbedtls/`, with a Doxygen description on the line before or after it. Use the `-0x` hex form. The regex skips decimal values silently, so the code would compile but never appear in `strerror` output. Pick an unused value; duplicates abort the generator.
2. **If the module is new**, add its prefix to `low_level_modules` or `high_level_modules` in `generate_errors.pl`, or the script exits with "Do not know how to handle". Its header name must be the lowercase module name, or the "has not been included" check fails. Its `MBEDTLS_<MOD>_C` config symbol must also exist.
3. **Regenerate `library/error.c`** with `perl scripts/generate_errors.pl` from the repo root, or just build with CMake. `library/error.c` is tracked in git, and `tests/scripts/check-generated-files.sh:135` diffs it against the generator output. So the regenerated file must be committed in the same change.
4. **Add a test row** to `tests/suites/test_suite_error.data` in the form `error_strerror:-0x....:"MODULE - description"`, with a `depends_on:` line for the module's config. That file is the specification for the output string.
5. **Run the tests** through the project's test task. I did not build or run anything here, so the generator run, the diff check and the test suite are unverified. I read the source and the index rather than executing them.