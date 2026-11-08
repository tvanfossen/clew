The string comes from a generated lookup table in `library/error.c`. The table is built from `#define`s in `include/mbedtls/*.h` by `scripts/generate_errors.pl`, so the path from a return value to text is a runtime path, and adding a new string is a header-and-generator job, not a `error.c` edit.

**Runtime path**

```
ret (e.g. -0x0022)
  │
  ▼ mbedtls_strerror(ret, buf, buflen)           library/error.c
  │   memset(buf, 0); ret = -ret                 → 0x0022
  │
  ├─ ret & 0xFF80 != 0 ?  (high-level module bits)
  │     mbedtls_high_level_strerr(ret)           switch on ret & 0xFF80
  │     → "SSL - ..."  or "UNKNOWN ERROR CODE (XXXX)"
  │     (SSL fatal-alert: return here, don't translate low bits)
  │
  ├─ low = ret & ~0xFF80 ; if 0 → done
  │     if high text exists, append " : "
  │     mbedtls_low_level_strerr(ret)           switch on ret & ~0xFF80
  │     → "AES - Invalid input data" or "UNKNOWN ERROR CODE (XXXX)"
```

A few details that matter:

- **Sign is stripped first.** Callers pass negative codes; the lookup switches on positive magnitudes, and the `case` labels are `-(MBEDTLS_ERR_...)`.
- **Two layers, one string.** A code can carry a high-level module part and a low-level part. The output is `"<high> : <low>"`, for example an SSL code combined with an X.509 or crypto code.
- **Unknown codes are not silent.** An unmatched code yields `UNKNOWN ERROR CODE (%04X)` with the masked value, and an unbuilt module simply falls out of the switch.
- **Callers** use `mbedtls_strerror(ret, buf, sizeof buf)` (declared in `include/mbedtls/error.h:165`). With `MBEDTLS_ERROR_C` off, it returns an empty string.

**Generation**

`library/error.c` is marked as auto-generated, between the `Begin/End Auto-Generated Code` markers in the template `scripts/data_files/error.fmt`. The Perl script:

1. Globs `include/mbedtls/*.h` and regex-matches `/** … */ #define MBEDTLS_ERR_X -0xNNNN /**< … */`. Each code needs exactly one doc comment, before or after the define, not both. The regex requires the `-0x` hex form, so a define written any other way is skipped without an error. Inference from the regex, not something I ran.
2. Takes the module name from the `MBEDTLS_ERR_<MODULE>_` prefix. Module names are checked against two hard-coded lists, `@low_level_modules` and `@high_level_modules`, and an unknown module aborts the run.
3. Wraps each module's cases in `#if defined(MBEDTLS_<MODULE>_C)` blocks and adds the matching `#include "mbedtls/<module>.h"`.
4. Emits `case -(NAME): return "MODULE - description";`, with the trailing period stripped and backslashes escaped.
5. Dies on a duplicate numeric value, and fails if a header defines codes but is not included.

Regeneration is wired into `library/Makefile`, `library/CMakeLists.txt` (the `GEN_FILES` option), and `tests/scripts/check-generated-files.sh`, which fails if the committed `error.c` differs from the generator's output.

**To add a new error code**

1. Pick an unused value in the owning module's range in `include/mbedtls/<module>.h`. The layout table at the top of `error.h` documents the allocation, and the generator does not check it. Only duplicates are caught.
2. Add `#define MBEDTLS_ERR_<MODULE>_<NAME> -0xNNNN` with a Doxygen `/**< ... */` or `/** ... */` description. The text becomes the user-visible string, so write it as the message.
3. If the module is new, add its name to the correct list in `scripts/generate_errors.pl` and make sure the `MBEDTLS_<MODULE>_C` guard exists.
4. Regenerate with `make -C library error.c` or the CMake `GEN_FILES` build, and commit the regenerated `library/error.c`. Do not hand-edit it.
5. Run `tests/scripts/check-generated-files.sh` to confirm the committed file matches the generator, and add a case to `tests/suites/test_suite_error.function` (the `error_strerror` test) for the new string.

The string the user sees is `"<MODULE> - <your description>"`, where `<MODULE>` is taken from the name prefix, so the name must follow `MBEDTLS_ERR_<MODULE>_`.