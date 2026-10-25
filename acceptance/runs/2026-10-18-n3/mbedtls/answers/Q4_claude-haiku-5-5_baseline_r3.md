**How a negative code becomes a string**

1. **Caller side.** A function returns a negative `MBEDTLS_ERR_*` value. The caller passes it to `mbedtls_strerror(ret, buf, buflen)`, declared in `include/mbedtls/error.h:165`. The `programs/` tools do this on error paths.

2. **Implementation.** `mbedtls_strerror` lives in `library/error.c`. It is a generated file; its header says so and it is built from `scripts/data_files/error.fmt`. The function:
   - Zeroes `buf` and negates `ret`, so `-0x40A0` becomes `0x40A0`.
   - Splits the value into two parts: the high-level part (`ret & 0xFF80`, the module) and the low-level part (`ret & ~0xFF80`, the module-specific code).
   - Looks up the high part with `mbedtls_high_level_strerr()` and the low part with `mbedtls_low_level_strerr()`. Each is a `switch` over `case -(MBEDTLS_ERR_...)` that returns a literal like `"RSA - Bad input parameters to function"`.
   - Joins the two with `" : "`. Unknown codes produce `UNKNOWN ERROR CODE (XXXX)`.
   - Returns early for `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`, since its low bits are not a sub-error.

   With `MBEDTLS_ERROR_C` disabled, a dummy version writes an empty string.

3. **Where the switch cases come from.** `scripts/generate_errors.pl` scans `include/mbedtls/*.h` for `#define MBEDTLS_ERR_xxx -0x....` lines. It takes the description from the Doxygen comment before or after the define, and it dies if a define has neither or both. It fills the `HEADER_INCLUDED`, `HIGH_LEVEL_CODE_CHECKS` and `LOW_LEVEL_CODE_CHECKS` placeholders in `error.fmt` and writes `library/error.c`. Build targets (`library/Makefile:355`, `library/CMakeLists.txt`, `make_generated_files.bat`) run it. `tests/scripts/check-generated-files.sh:135` regenerates and diffs it in CI.

**To add a new error code**

1. Add `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....` to the module's public header under `include/mbedtls/`. Give it exactly one Doxygen description, before (`/** ... */`) or after (`/*!< ... */`) the define. Don't use `\name` in that comment. The generator ignores that comment.
2. Pick a value inside the module's allocated range in the table at the top of `error.h`. Don't reuse a value; the generator dies on duplicates.
3. Make sure the module is in the generator's lists. `scripts/generate_errors.pl` has `@low_level_modules` and `@high_level_modules`. A module missing from both causes `Do not know how to handle: <MODULE>`. If the module is new, add it there and give it a `define_name` mapping if its `#if` guard isn't just `MBEDTLS_<MODULE>_C`.
4. Regenerate: `perl scripts/generate_errors.pl` from the repo root, or `make` in `library/`. Commit the regenerated `library/error.c` with the header change. Otherwise `check-generated-files.sh` fails.
5. Add a case to `tests/suites/test_suite_error.data`, in the form `error_strerror:-0x....:"MODULE - description"`, with the right `depends_on:` line. Run it through the repo's test flow; I have not run it here.

I did not build or run anything, so the generator and test steps above are from reading the scripts, not from executing them.