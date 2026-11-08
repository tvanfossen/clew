The string comes from a generated lookup table, not a hand-written one. `library/error.c` is produced from `include/mbedtls/*.h` by `scripts/generate_errors.pl`, and you never edit the table directly.

**Runtime path**

```
mbedtls_strerror(ret, buf, buflen)              library/error.c:792
  ret = -ret                                    (make it positive)
  ├─ high = ret & 0xFF80
  │    mbedtls_high_level_strerr(ret)           switch over (code & 0xFF80)
  │    NULL -> "UNKNOWN ERROR CODE (%04X)"
  │    SSL fatal alert? -> return early          (no low-level part is appended)
  └─ low = ret & ~0xFF80
       if low == 0 -> done (high-only error)
       if high text exists -> append " : "
       mbedtls_low_level_strerr(ret)            switch over (code & ~0xFF80)
       NULL -> "UNKNOWN ERROR CODE (%04X)"
```

The 16-bit code is split by the layout comment in `include/mbedtls/error.h:17-90`: 3 high-level module bits in `0xFF80`, and 7 low-level module bits below that. A caller can therefore get either half alone or both joined, e.g. `-0x40A0` becomes `"RSA - Bad input parameters to function : AES - Invalid key length"`. The test data in `tests/suites/test_suite_error.data` shows the exact expected strings.

**Where the table comes from**

1. Each public header declares codes as `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x00XX`, with one Doxygen description either before or after it (`include/mbedtls/aes.h:42-44` is an example).
2. `generate_errors.pl` scans every `include/mbedtls/*.h` for that pattern. It takes the module name from the identifier prefix. It also maps a few exceptions: `MPI`→`BIGNUM`, `CTR`→`CTR_DRBG`, `HMAC`→`HMAC_DRBG`, `NET`→`net_sockets`.
3. It emits one `case -(MBEDTLS_ERR_X): return "MODULE - description";` per code. Each case is wrapped in `#if defined(MBEDTLS_<MODULE>_C)`, and the header include is added to match.
4. `scripts/check-generated-files.sh` (line 135) reruns the generator and fails if `library/error.c` is out of date. Its `-u` flag rewrites the file instead.

**What a contributor has to do to add a new string**

1. **Add the define** in the module's public header, in the correct range from the layout table, with exactly one doxygen description (before or after). Update the layout table comment in `error.h` if you take a new range.
2. **Only for a brand-new module**, add its name to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`. Otherwise the generator exits with `Do not know how to handle`. The module's `MBEDTLS_<MODULE>_C` config symbol must exist, because the case is guarded by it.
3. **Regenerate** `library/error.c` with the generator (or `check-generated-files.sh -u`). Do not hand-edit the file, because the next regeneration overwrites it.
4. **Add a test case** in `tests/suites/test_suite_error.data`, with `depends_on:MBEDTLS_<MODULE>_C` and an `error_strerror:-0x....:"MODULE - text"` line. Write the test first and confirm it fails before the fix, per the repo's test conventions.

**Gotchas I confirmed in the script**

- The generator only enforces that codes are unique (`Duplicated error code`). It does not check that the value sits in the module's allotted range in `error.h`. That check is manual and depends on the layout comment.
- The description text is emitted verbatim (backslashes are escaped), so the wording you write in the doc comment is the wording callers see.
- A module with no `MBEDTLS_<MODULE>_C` symbol generates code that is compiled out, so its strings never appear.

I read the generator, the templates and the test data. I did not run the generator or the test suite, so the regeneration step and the exact pre-commit hook names are unverified here.