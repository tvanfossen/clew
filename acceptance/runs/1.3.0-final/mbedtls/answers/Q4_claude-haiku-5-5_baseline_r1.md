The string comes from a generated lookup table in `library/error.c`, and the table is built from the doc comments on the `MBEDTLS_ERR_*` defines in `include/mbedtls/*.h`. I read the code but did not build or run anything.

**Runtime path**

```
mbedtls_strerror(ret, buf, buflen)                     library/error.c:792
  ├─ buflen == 0 → return; else memset(buf, 0)
  ├─ ret = -ret                       (make it positive)
  ├─ high = ret & 0xFF80             (3-bit module ID)
  │    └─ mbedtls_high_level_strerr(ret)  → "CIPHER - Bad input parameters" | NULL
  │         NULL → "UNKNOWN ERROR CODE (%04X)"
  │       if high == SSL fatal alert → return (don't translate the low part)
  ├─ low = ret & ~0xFF80             (7-bit low-level code)
  │    └─ if low == 0 → return
  │       if high was written: append " : "
  │    └─ mbedtls_low_level_strerr(ret)  → "AES - ..." | NULL → "UNKNOWN ERROR CODE"
  └─ buf now holds e.g. "X509 - ... : ASN1 - ..."
```

The header comment in `include/mbedtls/error.h` documents the layout: 1 sign bit, 3 bits of high-level module ID, 5 bits of module-specific code, 7 bits of low-level code. A single return value can carry one high-level and one low-level code, which is why the output can be a two-part string joined by ` : `.

Both lookup functions are `switch` statements with `case -(MBEDTLS_ERR_X):` labels, wrapped in `#if defined(MBEDTLS_<MOD>_C)` guards. If a module is compiled out, its codes fall through to `UNKNOWN ERROR CODE`. If `MBEDTLS_ERROR_C` is off, `mbedtls_strerror` writes an empty string.

**How the switch is generated**

`scripts/generate_errors.pl` scans `include/mbedtls/*.h` with a regex for `#define MBEDTLS_ERR_<NAME> -0x....`. It takes the description from either a `/** ... */` comment before the define or a `/**< ... */` comment after it, and writes the result into `library/error.c` through the template `scripts/data_files/error.fmt`. The module name is the first word after `MBEDTLS_ERR_`, with three renames: `MPI` becomes `BIGNUM`, `CTR` becomes `CTR_DRBG`, and `HMAC` becomes `HMAC_DRBG`.

**What a contributor has to do to add one**

1. **Add the define** in the module's public header, for example `include/mbedtls/dhm.h`:
   ```c
   /** Making of the DHM parameters failed. */
   #define MBEDTLS_ERR_DHM_MAKE_PARAMS_FAILED  -0x3180
   ```
   - Give it exactly one doc comment, either before or after. The generator dies if it finds neither or both.
   - Pick an unused value in the module's range. The allocation table in `error.h` lists the ranges. I didn't check whether anything enforces that table beyond the duplicate check below.
   - The description is what ends up in the user-visible string. Write it as a short sentence without a trailing period; the generator strips one.
2. **Make sure the module is known to the generator.** `generate_errors.pl` keeps two hard-coded lists, `@low_level_modules` and `@high_level_modules`. A prefix not on either list makes the script print `Do not know how to handle` and exit 1. A brand-new module needs adding to the right list, and possibly to the `define_name` and `include_name` mappings.
3. **Regenerate `library/error.c`.** Run `perl scripts/generate_errors.pl` from the repo root, or use `scripts/make_generated_files.bat` on Windows. Do not hand-edit `error.c`.
4. **Pass the checks.** The generator fails on a duplicate code value. `tests/scripts/check-generated-files.sh` (line 135 covers `error.c`) fails if the committed file is stale. It runs in CI, so commit the regenerated file.
5. **Add a test and a changelog entry if it is user-visible.** `ChangeLog.d/00README.md` says to add an entry for user-visible changes. I did not locate the test suite file that covers error strings, so verify that before writing a test.