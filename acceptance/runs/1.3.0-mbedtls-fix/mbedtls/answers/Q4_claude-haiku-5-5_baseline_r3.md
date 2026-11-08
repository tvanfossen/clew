The string lookup is in `library/error.c`, and that file is generated. Here is the path from a negative return code to text, and the steps to add one.

**Runtime path**

1. A function returns a negative int such as `MBEDTLS_ERR_SSL_BAD_INPUT_DATA` (`-0x7100`). The caller passes it to `mbedtls_strerror(ret, buf, buflen)`, defined at `library/error.c:792`.
2. `mbedtls_strerror` clears the buffer, then takes the absolute value. Negative codes are never looked up with their sign.
3. It splits the code on the 0xFF80 mask. The high-level bits (module, e.g. SSL, X.509, PK) go to `mbedtls_high_level_strerr()`. The low-level bits (e.g. AES, BIGNUM, ASN.1) go to `mbedtls_low_level_strerr()`, which masks with `~0xFF80`.
4. Each lookup is a `switch` over `case -(MBEDTLS_ERR_...)` that returns a string like `"SSL - Bad input parameters to function"`. Unknown codes produce `"UNKNOWN ERROR CODE (%04X)"`.
5. If both halves are present, the output is `high : low`. There is one exception: a fatal SSL alert returns after the high-level part and skips the low-level part.
6. If `MBEDTLS_ERROR_C` is disabled, the dummy version at line 867 just writes an empty string.

**Generation**

`library/error.c` is produced by `scripts/generate_errors.pl` from `scripts/data_files/error.fmt`. The Makefile target is at `library/Makefile:355-360`, and `library/CMakeLists.txt:136-144` does the same. The script:

- scans every `include/mbedtls/*.h` for `#define MBEDTLS_ERR_XXX -0x....` lines
- takes the description from a Doxygen `/*!<` or `/**` comment, requiring exactly one of the two
- rejects duplicate numeric values
- groups each code under its module (`MBEDTLS_ERR_<MODULE>_...`) and wraps the cases in `#if defined(MBEDTLS_<MODULE>_C)`
- aborts if a header that defines codes is not included by `error.c`

**To add a new code**

1. Add `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....` to the matching header in `include/mbedtls/`, with a `/*!< ... */` description on the same line. The value must be unused and must be a negative literal in the same format as its neighbours.
2. If the module is new, add it to `@low_level_modules` or `@high_level_modules` in `generate_errors.pl`. The script exits with an error otherwise. Also add the name to the `$define_name` / `$include_name` special cases if the header or config symbol doesn't follow the default pattern.
3. Regenerate `library/error.c` through the build system (`make -C library error.c`, or the CMake build). Do not hand-edit `error.c`. The `error.c` target depends on the headers, so the build regenerates it when they change.
4. Run the project's gate through pre-commit, as the repo's tooling expects. Since `error.c` is committed, the regenerated file must be included in the change.
5. Add a test in the `error` test suite (`tests/suites/test_suite_error.function`), which already covers `mbedtls_strerror`, so the new string is checked.

I did not run the generator or a build, so the regeneration steps and the test name are from reading the source, not from a run.