**How a negative code becomes a string**

1. `mbedtls_strerror(errnum, buf, buflen)` in `library/error.c` takes the absolute value of the code, zeroes the buffer, and splits the value into two parts:
   - **High-level part** (`ret & 0xFF80`): looked up with `mbedtls_high_level_strerr()`, a `switch` over module-level codes such as `-0x4080` → `"RSA - Bad input parameters to function"`.
   - **Low-level part** (`ret & ~0xFF80`): looked up with `mbedtls_low_level_strerr()`, a second `switch` for codes such as `-0x0020` → `"AES - Invalid key length"`.
2. If both parts are present, the two strings are joined with `" : "`. An SSL fatal-alert code returns early and skips the low-level part.
3. Any part without a table entry becomes `"UNKNOWN ERROR CODE (%04X)"`.
4. If `MBEDTLS_ERROR_C` is disabled, the dummy `mbedtls_strerror` returns an empty string.

The `switch` bodies are not hand-written. They sit between `/* Begin Auto-Generated Code. */` and `/* End Auto-Generated Code. */` in `library/error.c`, and `scripts/generate_errors.pl` produces them.

**How the generator builds the table**

The script reads `include/mbedtls/*.h` and matches each `#define MBEDTLS_ERR_<NAME> -0x....` together with a Doxygen description. The description must be given either before the define (`/** ... */`) or after it (`/**< ... */`), not both. The script then:
- Dies on a duplicate code value.
- Dies on a module prefix that is not in its `@low_level_modules` or `@high_level_modules` list.
- Emits `case -(NAME): return "MODULE - description";` and the matching `#if defined(MBEDTLS_..._C)` guards and `#include`s.
- Writes the result to `library/error.c` using the template `scripts/data_files/error.fmt`.

**What a contributor does to add one**

1. Pick an unused code in the right range. The block comment at the top of `include/mbedtls/error.h` lists the module IDs and ranges, and the high-level and low-level layouts differ.
2. Add the `#define` to the module's header, with a one-line Doxygen description. Do not put the module name in the description, because the script adds `MODULE - ` itself.
3. If the module prefix is new, add it to the module lists in `generate_errors.pl` and set its guard and include mapping. The existing aliases (`MPI`, `CTR`, `HMAC`, `NET`) show the pattern.
4. Regenerate with the library build target (`make error.c` in `library/`, or the CMake rule), or run `scripts/generate_errors.pl` from the repo root. Do not edit the generated block by hand.
5. Add a case to `tests/suites/test_suite_error.data`, for example `error_strerror:-0x....:"MODULE - description"`. Also update the count and range notes in `error.h`.
6. Verify through the repo's checks. CI runs `tests/scripts/check-generated-files.sh`, which regenerates `error.c` and diffs it, so a stale `error.c` fails there. Run the error test suite too.

I read the code but did not run the generator or the tests, so the exact make target names and the test-suite invocation are unverified here.