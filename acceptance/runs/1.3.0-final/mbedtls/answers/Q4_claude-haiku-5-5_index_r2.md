**Short answer:** the string comes from a generated `switch` in `library/error.c`. A contributor adds a `#define MBEDTLS_ERR_*` with a doc comment in the module header, then regenerates `error.c` with `scripts/generate_errors.pl`. Don't hand-edit `error.c`.

## Caller to string

```
caller: ret = mbedtls_foo(...)           // ret < 0, e.g. -0x4E80
   │
   ▼
mbedtls_strerror(ret, buf, buflen)       library/error.c:792
   │  buflen==0 → return; zero buf; ret = -ret
   │
   ├─ ret & 0xFF80 ?  (high-level part: module ID bits)
   │     └─ mbedtls_high_level_strerr(ret)   error.c:174  → "SSL - ..."  (or "UNKNOWN ERROR CODE (xxxx)")
   │        └─ if SSL fatal alert: return here (no low-level part)
   │
   ├─ use_ret = ret & ~0xFF80  (low-level part: 7 bits)
   │     └─ if 0 → done
   │
   └─ if high-level text exists, append " : " then
         mbedtls_low_level_strerr(ret)      error.c:537  → "MPI - ..." (or UNKNOWN)
```

Points to know:

- **Sign is stripped first.** Callers pass negative values, and the tables are keyed on the negated constants.
- **The code is split in two.** `error.h` documents the layout: the high bits name a module (`0xFF80`), and the low 7 bits are a low-level error (`0x007F`). An error can carry both, so the output is `HIGH : LOW`.
- **Both lookups are generated `switch` statements** between `/* Begin Auto-Generated Code. */` and `/* End Auto-Generated Code. */`. Each case is wrapped in `#if defined(MBEDTLS_<MOD>_C)`, so a disabled module has no string and falls through to `UNKNOWN ERROR CODE (%04X)`.
- **Gating.** The whole file is compiled only when `MBEDTLS_ERROR_C` or `MBEDTLS_ERROR_STRERROR_DUMMY` is set. With `MBEDTLS_ERROR_C` off, the dummy `mbedtls_strerror` just writes an empty string.

## Adding a new error code

1. **Define the code** in `include/mbedtls/<module>.h`, following the existing pattern:
   ```c
   /** Invalid key length. */
   #define MBEDTLS_ERR_AES_INVALID_KEY_LENGTH   -0x0020
   ```
   - The value must be a negative hex literal (`-0x....`). The generator's regex only matches that form, so a decimal value is skipped without any error and simply gets no string.
   - Put the description in exactly one place: a `/** ... */` before the define or a `/*!< ... */` after it. Neither or both is a hard failure.
   - Pick an unused number from the module's range. The table in `error.h` (around lines 37–54) lists what's assigned. A duplicate value is a hard failure.

2. **If the module is new**, add its name to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`. An unknown module makes the script exit with `Do not know how to handle`. The header must be named after the lowercase module (`net_sockets` is the one special case). Add a row for the module in the `error.h` table as well, since that table is maintained by hand.

3. **Regenerate.** `library/Makefile` has a rule that rebuilds `error.c` whenever a header in `include/mbedtls/` changes, so a normal build does it. You can also run `perl scripts/generate_errors.pl` from the repo root. The generator fails if any header defines codes but isn't included.

4. **Check the output.** `tests/scripts/check-generated-files.sh` re-runs the generator and diffs the result against the committed `error.c`, so the committed file has to match what the script produces.

I read this from source and did not build or run the generator, so the regex and table claims are from reading the code, not from a test run.