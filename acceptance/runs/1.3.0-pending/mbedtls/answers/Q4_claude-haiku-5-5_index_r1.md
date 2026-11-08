The string comes from a generated table, not from any hand-written mapping. Your caller passes the negative int to `mbedtls_strerror()`, and that walks through three layers.

```
header  include/mbedtls/*.h          #define MBEDTLS_ERR_<MOD>_<X> -0x00NN  /**< doc */
   │
   │  scripts/generate_errors.pl   (run by library/Makefile, library/CMakeLists.txt, make_generated_files.bat)
   │  + scripts/data_files/error.fmt (template)
   ▼
library/error.c  (generated, checked in)
   mbedtls_high_level_strerr()  switch on ret & 0xFF80
   mbedtls_low_level_strerr()   switch on ret & ~0xFF80
   │
   ▼
mbedtls_strerror(ret, buf, buflen)  (library/error.c:792)
   ret = -ret; → high-level string, then " : ", then low-level string
```

**Runtime path (`library/error.c:792`)**

1. `mbedtls_strerror` returns early if `buflen == 0`, then zeroes the buffer.
2. It flips the sign (`ret = -ret`), so `-0x6080` and `0x6080` decode the same.
3. If `ret & 0xFF80` is set, it looks up the high-level part (the module, e.g. `SSL`, `X509`, `RSA`) with `mbedtls_high_level_strerr()`. An unknown code prints `UNKNOWN ERROR CODE (%04X)`.
4. There is a special case: if the high-level part is `-(MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE)`, it returns without decoding the low-level part (only when `MBEDTLS_SSL_TLS_C` is on).
5. It takes the remainder `ret & ~0xFF80`. If that is zero, it returns the high-level text alone.
6. Otherwise it appends `" : "` and the low-level text from `mbedtls_low_level_strerr()`, again printing `UNKNOWN ERROR CODE` on a miss.

Each lookup is a `switch` over `case -(MBEDTLS_ERR_X):` with `return "MODULE - description";`. So `MBEDTLS_ERR_ERROR_GENERIC_ERROR` (`-0x0001`) decodes to `"ERROR - Generic error"` (`library/error.c:665`).

**Generation (`scripts/generate_errors.pl`)**

The script scans `include/mbedtls/*.h` with a regex for `#define MBEDTLS_ERR_\w+ -0x...`. Each definition needs a Doxygen comment, either before it or as a `/**<` after-comment, but not both. It refuses a duplicate value, and it exits non-zero if a header defines codes without being in the include list. It then emits:

- `case` lines grouped under `#if defined(MBEDTLS_<MOD>_C)` guards, so the string exists only when that module is compiled in;
- an `#include "mbedtls/<module>.h"` for each module that has codes.

**Adding a new code**

1. **Pick the range.** Use the module's block in the table at the top of `include/mbedtls/error.h`. Generic codes live in `error.h`, and module codes sit in the module's own header (e.g. `foo.h`).
2. **Add the define** with a Doxygen description, before or after, matching the convention in `error.h:98`. A value that is already used is a hard error.
3. **Check the module is registered.** If the prefix is new, add it to `@low_level_modules` or `@high_level_modules` in `generate_errors.pl`. Otherwise the script prints "Do not know how to handle" and exits 1. A new header also needs its include name derived from the module name (lowercased, with the two special cases for `NET` and the renamed `MPI`/`CTR`/`HMAC`).
4. **Regenerate `library/error.c`.** Run it through the build: `make` in `library/` or the CMake `GEN_FILES` target. Don't hand-edit `error.c`.
5. **Commit both the header and the regenerated `error.c`.** `tests/scripts/check-generated-files.sh:135` checks that the checked-in `error.c` matches the generator output.

Two caveats for the caller: the generated string is only present when the defining module's `MBEDTLS_*_C` config is enabled, and the buffer is always null-terminated but may be truncated.

I did not modify anything in the repository, and I did not run the generator or the build. The description above is from reading the source.