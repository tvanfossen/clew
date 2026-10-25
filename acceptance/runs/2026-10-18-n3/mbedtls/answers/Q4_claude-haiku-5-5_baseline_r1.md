**Short version:** the strings are generated at build time from the `#define`s in the public headers. At runtime, `mbedtls_strerror()` splits the code into a high-level (module) part and a low-level (specific error) part, and looks each up in a `switch`.

### Runtime path

```
ret (e.g. -0x7100)
  │
  ▼
mbedtls_strerror(ret, buf, buflen)            library/error.c
  │  memset buf to 0, take ret = -ret
  │
  ├─ ret & 0xFF80 ≠ 0 ?  (high-level/module bits)
  │     └─ mbedtls_high_level_strerr(ret)    switch on ret & 0xFF80
  │          → "SSL - ..."  (or "UNKNOWN ERROR CODE (XXXX)")
  │     └─ SSL fatal-alert early return
  │
  ├─ ret & ~0xFF80 ≠ 0 ?  (low-level bits)
  │     └─ append " : " if buf already has text
  │     └─ mbedtls_low_level_strerr(ret)     switch on ret & ~0xFF80
  │          → "AES - ..."  (or "UNKNOWN ERROR CODE (XXXX)")
  │
  └─ result: one string, e.g. "SSL - Bad input parameters to function : ..."
```

Notes on the walk-through:
- The sign is stripped first, so callers can pass either `-0x7100` or `0x7100`.
- Both lookups are generated `switch` statements. `case -(MBEDTLS_ERR_X):` returns `"MODULE - description"`.
- If the library was built without `MBEDTLS_ERROR_C` (and not with `MBEDTLS_ERROR_STRERROR_DUMMY`), the function is a stub that returns an empty string.

### Build-time generation

`library/error.c` is not hand-written. It is produced by `scripts/generate_errors.pl` from `scripts/data_files/error.fmt`, and the Makefile (`library/Makefile:355-360`) and CMake (`library/CMakeLists.txt:136-144`) regenerate it when headers change. The script:
1. Scans `include/mbedtls/*.h` for lines like `#define MBEDTLS_ERR_FOO -0x1234`.
2. Takes the description from a Doxygen comment, either `/*!<` after the define or `/**` before it. A define with neither dies. Having both also dies.
3. Dies on duplicate values.
4. Maps the name prefix to a module (`MBEDTLS_ERR_<MODULE>_...`). Modules must be listed in `@low_level_modules` or `@high_level_modules` in the script, or it exits with `Do not know how to handle`.
5. Wraps each module's cases in `#if defined(MBEDTLS_<MODULE>_C)` and adds `#include "mbedtls/<module>.h"` for the headers that define codes.
6. Errors if a header defines codes but is not included.

### What a contributor has to do

1. **Add the define** in the right public header, e.g. `include/mbedtls/<module>.h`:
   ```c
   /** Description of the failure, ending without a period. */
   #define MBEDTLS_ERR_FOO_BAR    -0x1234
   ```
   Use a free value in that module's range and make sure it fits the high/low split. The high-level bits are `0xFF80` and the low-level bits are `0x007F`.
2. **Use the right form for the description.** Put a `/*!< ... */` comment on the same line, or a `/** ... */` comment above. Don't use both.
3. **If it is a new module,** add its name to the right list in `scripts/generate_errors.pl`. Also add the matching `#if` / include handling only if the module is new, since the script generates it.
4. **Regenerate** with `make` in `library/`, or let CMake run it. Don't edit `library/error.c` directly. Note that the generated file was not regenerated or diffed here, so this is from reading the scripts.
5. **Run the tests** through the project's normal workflow. The error test suite is `tests/suites/test_suite_error.function`. I did not inspect it for coverage of new codes.

The repo also has `programs/util/strerror.c`, a small CLI that calls `mbedtls_strerror` on a code passed on the command line. It's handy for checking a new string by hand.