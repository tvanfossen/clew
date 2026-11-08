The short answer: `error.c` contains two generated lookup tables, and a new error string comes from a `#define` in the module's header, not from editing `error.c`.

**Runtime path**

```
ret (e.g. -0x2880)
  │
mbedtls_strerror(ret, buf, buflen)        library/error.c:792
  ├─ ret = -ret                           sign removed
  ├─ high = ret & 0xFF80                  module/category bits
  │    └─ mbedtls_high_level_strerr()     error.c:174  switch → "X509 - ..."
  │       (if SSL fatal alert: stop here, skip low-level)
  ├─ low  = ret & ~0xFF80                 module-specific bits
  │    └─ mbedtls_low_level_strerr()      error.c:537  switch → "AES - ..."
  └─ join with " : ", or "UNKNOWN ERROR CODE (XXXX)" when no case matches
```

The `switch` cases inside those two functions are generated. They sit between the `Begin/End Auto-Generated Code` markers at `error.c:186–528` (high) and `error.c:549–783` (low). When `MBEDTLS_ERROR_C` is off, a dummy `mbedtls_strerror` at `error.c:867` just writes an empty string.

**How the tables are generated**

`scripts/generate_errors.pl` runs from `library/Makefile:355–360`, and `error.c` depends on every `include/mbedtls/*.h`, so a header edit triggers regeneration on the next build. The script:

- scans `include/mbedtls/*.h` for `#define MBEDTLS_ERR_<X> -0x....`
- takes the description from a `/** ... */` comment before the define or a `/*!< ... */` after it, and dies if there is neither or both
- builds the string as `"<MODULE> - <description>"`, with the module taken from the name prefix
- dies on a duplicate code
- dies with "Do not know how to handle" if the module is not in its `@low_level_modules` or `@high_level_modules` lists

**What a contributor does to add one**

1. Add the define to the module's header in `include/mbedtls/<module>.h`, with a negative hex value in an unused slot and a doc comment. Check the module's range in the layout table at the top of `include/mbedtls/error.h`, lines 17–80, and update it. That table is documentation; I did not find the generator reading it.
2. If the module is new, add it to the right list in `scripts/generate_errors.pl`. Low-level modules get the 0x0001–0x007F space and high-level ones the 0xXX80 space.
3. Regenerate with the library build (`make` in `library/`, or the CMake target). Do not hand-edit `error.c`.
4. Commit the regenerated `library/error.c`. `tests/scripts/check-generated-files.sh:135` regenerates it and fails CI on a diff.
5. Add a case to `tests/suites/test_suite_error.data` (it calls `error_strerror` in `test_suite_error.function`), and check `ChangeLog.d/00README.md` for the changelog entry format. I did not read that README.

I did not build or run anything, so the regeneration step and the tests are unverified here.