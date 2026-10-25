**Short version:** `mbedtls_strerror()` in `library/error.c` turns the integer into text by splitting it into a high-level module part and a low-level part, then looking each part up in a `switch`. That `switch` is generated from the `MBEDTLS_ERR_*` defines in `include/mbedtls/*.h` by `scripts/generate_errors.pl`. You never edit `error.c` by hand.

**Runtime path**

```
ret (e.g. -0x6100 | -0x0020 = -0x6120)
  │
  ▼
mbedtls_strerror(ret, buf, buflen)            library/error.c
  │  ret = -ret           (drop sign)
  │
  ├─ ret & 0xFF80 ?  ──► high-level: mbedtls_high_level_strerr(ret)
  │                       switch on (ret & 0xFF80)  → "CIPHER - Bad input data"
  │                       (no match → "UNKNOWN ERROR CODE (XXXX)")
  │     └─ if it's MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE → return early
  │
  ├─ ret & ~0xFF80 == 0 ? → done
  │
  └─ append " : " then low-level: mbedtls_low_level_strerr(ret)
                           switch on (ret & ~0xFF80) → "AES - Invalid key length"
                           (no match → "UNKNOWN ERROR CODE (XXXX)")
```

So `-0x6120` becomes `CIPHER - Bad input data : AES - Invalid key length`. The public entry point is declared at `include/mbedtls/error.h:165`. The `MBEDTLS_ERROR_C` and `MBEDTLS_ERROR_STRERROR_DUMMY` config switches decide whether the real table is compiled in or an empty stub is used.

**Generation path**

1. Each header defines codes as `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....`, with a Doxygen `/**<` or `/**` description. Example: `include/mbedtls/cipher.h:40`.
2. `scripts/generate_errors.pl` scans every `include/mbedtls/*.h` with a regex. It takes the name, the hex value and the description.
3. It fills `scripts/data_files/error.fmt` placeholders (`HEADER_INCLUDED`, `LOW_LEVEL_CODE_CHECKS`, `HIGH_LEVEL_CODE_CHECKS`) and writes `library/error.c`.
4. Build systems regenerate it. The Makefile rule is at `library/Makefile:355`, the CMake rule at `library/CMakeLists.txt:136`, and the Windows path is `scripts/make_generated_files.bat`.
5. `library/error.c` is tracked in git (the `.gitignore` entry is commented out). `tests/scripts/check-generated-files.sh:135` fails CI if the committed file doesn't match what the script produces.

**What a contributor must do to add a new error code**

1. **Add the define** in the right header under `include/mbedtls/`, with a negative hex value that doesn't collide with an existing one. Follow the module's range comment, e.g. `/* Error codes in range 0x0020-0x0022 */` in `aes.h`.
2. **Write exactly one description comment**, either before the define (`/**< ... */` or `/** ... */`) or after it (`/**< ... */`). The script dies if there is neither or both. Descriptions containing a `\name` tag are ignored, so don't use that form for the description.
3. **Check the module name.** The prefix after `MBEDTLS_ERR_` must be in the `@low_level_modules` or `@high_level_modules` list at the top of `generate_errors.pl`. Otherwise the script exits with `Do not know how to handle`. A brand-new module must be added to one of those lists. Its header must also be in the include table, or the script reports the header as not included.
4. **Regenerate `library/error.c`** through the normal build (`make` in `library/`, or the CMake GEN_FILES target), or by running `scripts/generate_errors.pl` from the repo root. Commit the regenerated `error.c` together with the header change. Otherwise `check-generated-files.sh` fails.
5. **Add a test** in the error test suite (`tests/suites/test_suite_error.function`, which uses `error_strerror()`). Assert the exact string the code produces.

Two caveats from reading the code. I did not run the generator or the test suite, so the steps above are from the source only. I also didn't check whether the high-level/low-level split logic in `mbedtls_strerror` has edge cases for codes that set bits in both ranges. It works for the codes I looked at.