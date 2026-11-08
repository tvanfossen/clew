**Short version:** `library/error.c` is generated from the `MBEDTLS_ERR_*` defines in `include/mbedtls/*.h`. A negative code is negated, split into a high-level part (module) and a low-level part (sub-error), and each part is looked up in a `switch` that the generator wrote. Adding a string means adding a define with a doc comment, regenerating `error.c`, and adding a test row.

## How a code becomes text

```
int ret = -0x40A0           (caller, e.g. programs/ssl/ssl_client1.c)
   │
   ▼
mbedtls_strerror(ret, buf, buflen)            library/error.c:792
   │  memset(buf, 0); ret = -ret  → 0x40A0
   │
   ├─ ret & 0xFF80 ≠ 0 ?  (high-level part = 0x4080)
   │     └─ mbedtls_high_level_strerr(ret)    switch(0x4080) → "RSA - Bad input parameters to function"
   │          NULL → "UNKNOWN ERROR CODE (XXXX)"
   │     └─ if it is -(MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE): return early (no low-level text)
   │
   ├─ ret & ~0xFF80 ≠ 0 ?  (low-level part = 0x0020)
   │     └─ append " : "
   │     └─ mbedtls_low_level_strerr(ret)    switch(0x0020) → "AES - Invalid key length"
   │          NULL → "UNKNOWN ERROR CODE (XXXX)"
   ▼
buf = "RSA - Bad input parameters to function : AES - Invalid key length"
```

The `0xFF80` mask is the split. Module codes with bits in `0xFF80` are "high-level" (RSA, SSL, X509, and so on). Codes in the low 7 bits are "low-level" (AES, ASN1, BASE64, and so on). A combined code like `-0x40A0` carries both. The test at `tests/suites/test_suite_error.data` checks exactly that combined case. `buflen` is respected by `mbedtls_snprintf`, so long output is truncated, not overflowed.

Where the table comes from: `scripts/generate_errors.pl` scans every `include/mbedtls/*.h` for `#define MBEDTLS_ERR_\w+ -0x...` lines. It emits a `case -(NAME): return "MODULE - description";` line for each one into `scripts/data_files/error.fmt`, and writes the result to `library/error.c`. The generator is wired into `library/Makefile`, `library/CMakeLists.txt` (when `GEN_FILES` is on), and `scripts/bump_version.sh`.

## Adding a new error string

1. **Define the code** in the module's header, e.g. `include/mbedtls/rsa.h`:
   ```c
   /** Something failed during generation of a key. */
   #define MBEDTLS_ERR_RSA_KEY_GEN_FAILED  -0x4180
   ```
   The generator requires a description in exactly one place: either a `/** */` comment before the define or a `/*!< */` comment after it. Neither or both is a hard error. The text is copied verbatim, with the trailing period stripped and the module prefix added automatically. The value must be unique across the tree, or the generator dies with "Duplicated error code".

2. **Pick a value in the right slot.** The generator does not check that a low-level code stays under `0x80` or that a high-level code sits on the module's `0x80` boundary. Nothing catches a mistake here except lookup misrouting, so follow the existing values in the same header.

3. **If the module is new**, it also needs:
   - An entry in `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`. Otherwise the script prints "Do not know how to handle" and exits 1.
   - A header-name mapping, since the include is derived by lowercasing the module name. Irregular cases are special-cased (`MPI`→bignum, `NET`→`net_sockets.h`, and others).
   - A config-guard entry in `define_name`, so `error.c` wraps the `#include` and the `case` block in the right `MBEDTLS_<MOD>_C` guard.

4. **Regenerate** `library/error.c` with the normal build (`make` in `library/`, or the CMake `GEN_FILES` target). Do not hand-edit it. Commit the header and the regenerated `library/error.c` together. `error.c` is tracked in git, and `tests/scripts/check-generated-files.sh` regenerates it and fails if the committed copy differs.

5. **Add a test row** to `tests/suites/test_suite_error.data`, following the existing format:
   ```
   New module error
   depends_on:MBEDTLS_RSA_C
   error_strerror:-0x4180:"RSA - Something failed during generation of a key"
   ```
   Write it first and watch it fail, per the repo's test-as-spec practice. It runs through the `error_strerror` suite function, which calls `mbedtls_strerror` into a 500-byte buffer and compares the result.

If the new code needs combining with a low-level code, a row like the existing `-0x40A0` case covers the concatenation path too.

I read the generator, `error.c`, the header defines, the build rules and the test suite. I did not build the library or run the tests, so the regeneration and test steps above are described from the source, not verified by execution.