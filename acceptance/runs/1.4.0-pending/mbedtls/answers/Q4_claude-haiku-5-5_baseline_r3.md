The string comes from a generated lookup table in `library/error.c`. Nothing parses the number at runtime, and there is no registry to update by hand.

**Runtime path**

```
ret = -0x7100
  └─ mbedtls_strerror(ret, buf, buflen)            library/error.c
       ├─ ret = -ret                                  sign stripped
       ├─ high = ret & 0xFF80  (0x7100)              module bits
       │    └─ mbedtls_high_level_strerr(ret)        switch on high bits
       │         → "SSL - Bad input..." or NULL
       ├─ low  = ret & ~0xFF80 (0x0000)              low-level bits
       │    └─ if non-zero: mbedtls_low_level_strerr → appended after " : "
       └─ NULL on either side → "UNKNOWN ERROR CODE (%04X)"
```

- `mbedtls_strerror` is the public entry point, declared in `include/mbedtls/error.h`. It clears `buf`, takes the absolute value, and splits the 16-bit code into a high-level part (`0xFF80` mask) and a low-level part (the complement).
- Each half goes through a `switch` of `case -(MBEDTLS_ERR_...): return "MODULE - description";`. Those switches live in `library/error.c`, which is generated.
- If both halves are present, the output is `"High - desc : Low - desc"`. The one exception is `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`, which returns early so the low-level alert code is not translated.
- If `MBEDTLS_ERROR_C` is disabled, a dummy version writes an empty string.

**Generation path**

`library/error.c` is not hand-edited. `scripts/generate_errors.pl` builds it from:

1. `include/mbedtls/*.h`: it regex-scans for `#define MBEDTLS_ERR_<MODULE>_<NAME> -0xNNNN` and requires a Doxygen description either before or after the define, but not both.
2. `scripts/data_files/error.fmt`: the template. The script fills in the `HEADER_INCLUDED`, `HIGH_LEVEL_CODE_CHECKS` and `LOW_LEVEL_CODE_CHECKS` placeholders.

Module names come from the prefix (`MPI` maps to `BIGNUM`, `SSL` maps to `SSL_TLS`, and so on). The generator exits with an error on unknown modules, duplicate values, or a missing description. The Makefile and CMake both regenerate `error.c` when headers change. `tests/scripts/check-generated-files.sh` fails CI if the checked-in `error.c` differs from what the generator produces.

**What a contributor does to add one**

1. Add `#define MBEDTLS_ERR_<MODULE>_<NAME> -0xNNNN` to the module's public header, in the range that module owns (see the layout table in `error.h`). Use an unused value. Add one Doxygen comment, before or after, not both.
2. If the module is new, add it to the `@low_level_modules` or `@high_level_modules` list in `generate_errors.pl` and add its `#include` mapping. A new module also needs a matching `MBEDTLS_<MODULE>_C` guard, which the generator emits.
3. Regenerate with `perl scripts/generate_errors.pl` (or `make` in `library/`) and commit the updated `library/error.c`. Otherwise the generated-files check fails.
4. Add a case to `tests/suites/test_suite_error.data` in the form `error_strerror:-0xNNNN:"MODULE - text"`. Per the repo's rule, add it first and see it fail before the header change.
5. Add a `ChangeLog.d/*.txt` entry if the change is user-visible, which a new error code usually is.

I did not run the generator or the test suite; this is from reading the source.