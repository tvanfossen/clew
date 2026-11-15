The string comes from a generated lookup table, not hand-written code. The only hand-maintained inputs are the `#define`s in the public headers and the module lists in `generate_errors.pl`.

**Lookup path for a negative code**

```
mbedtls_xxx() returns e.g. -0x4E80 (MBEDTLS_ERR_X509_... | MBEDTLS_ERR_ASN1_...)
  │
  ▼
mbedtls_strerror(ret, buf, buflen)              library/error.c:792
  ├─ ret = -ret                                   (make positive)
  ├─ high = ret & 0xFF80 → mbedtls_high_level_strerr()
  │     switch(case -(MBEDTLS_ERR_X509_...)) → "X509 - ..."
  ├─ (SSL fatal alert → return early, skip low level)
  ├─ low  = ret & ~0xFF80 → mbedtls_low_level_strerr()
  │     switch(case -(MBEDTLS_ERR_ASN1_...)) → "ASN1 - ..."
  └─ join as "high : low" into buf (or whichever part exists;
     unknown parts become "UNKNOWN ERROR CODE (%04X)")
```

The 16-bit layout (documented in `include/mbedtls/error.h:17-60`) splits the code into a 3-bit high-level module (mask `0xFF80`) and a 7-bit low-level module. That is why one return value can carry two names. The `-` sign is stripped before any matching, so the switch cases are written as `case -(MBEDTLS_ERR_...)`.

**How the table is produced**

`scripts/generate_errors.pl` scans every `include/mbedtls/*.h` for `#define MBEDTLS_ERR_<X> -0x....` lines. It takes the description from a Doxygen comment placed either before or after the define (not both), and it emits `library/error.c` from `scripts/data_files/error.fmt`. `library/error.c` is therefore generated. Editing it by hand will be overwritten.

**What a contributor has to do to add a new code**

1. **Define it** in the module's public header, e.g. `include/mbedtls/asn1.h`:
   ```c
   /** Out of data when parsing an ASN1 data structure. */
   #define MBEDTLS_ERR_ASN1_OUT_OF_DATA   -0x0060
   ```
   Pick an unused value from the module's range in the table in `error.h`. Give it exactly one description comment, before or after. Keep the name in the form `MBEDTLS_ERR_<MODULE>_<NAME>`, because the module is taken from the prefix.
2. **New module only:** add its name to `@low_level_modules` or `@high_level_modules` in `generate_errors.pl`. Otherwise the script exits with `Do not know how to handle`. The generator also needs the module's header to be `#include`d from `error.c`. It derives the header name from the module name, with a few special cases such as `NET → net_sockets.h`, and fails with `has not been included` if that is missing from the generated includes.
3. **Regenerate** `library/error.c`. The build does this through the `error.c` rule in `library/Makefile` and the CMake equivalent. You can also run `perl scripts/generate_errors.pl` from the repo root. Commit the regenerated file.
4. **Verify.** `tests/scripts/check-generated-files.sh` regenerates the file and fails CI if the committed copy is stale. The generator also rejects duplicate values, so reusing a number is caught at generation time.
5. **Update the range table** in `error.h`, if the new code takes a value that the table documents.

Two cautions. The description string is the user-visible text, so keep it short and sentence-like. Trailing periods are stripped, and backslashes are escaped. Also, I did not open `tests/suites/test_suite_error.data`, so I can't say how the existing tests exercise these strings. The `.function` file is the place to look when adding coverage.