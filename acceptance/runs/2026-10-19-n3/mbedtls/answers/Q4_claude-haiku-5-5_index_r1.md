The path runs from one public function through two generated lookup tables, and the tables are regenerated from the header comments, so a contributor edits headers and the generator script, not `library/error.c`.

```
mbedtls_strerror(ret, buf, buflen)          library/error.c:792
 ├─ buflen==0 → return; memset(buf,0)
 ├─ ret = -ret                              (strip sign)
 ├─ ret & 0xFF80 ?  → mbedtls_high_level_strerr(ret)   error.c:174
 │                    "MODULE - description" into buf
 │                    (SSL fatal alert → return here, no low part)
 ├─ ret & ~0xFF80 ? → append " : " then
 │                    mbedtls_low_level_strerr(ret)    error.c:537
 │                    "MODULE - description"
 └─ unknown code at either level → "UNKNOWN ERROR CODE (%04X)"
```

**Runtime path**

1. A caller passes the negative return value, a buffer, and its length to `mbedtls_strerror` (`library/error.c:792`). It clears the buffer and makes the code positive.
2. The code is split into two halves. Bits `0xFF80` select the high-level part, which is a module such as CIPHER, SSL or X509. Bits `~0xFF80` (`0x0001`–`0x007F`) select the low-level part, which is a module such as AES, ASN1 or BIGNUM.
3. Each half is looked up in a `switch` (`mbedtls_high_level_strerr` at `error.c:174`, `mbedtls_low_level_strerr` at `error.c:537`). Each `case` returns a string of the form `"MODULE - description"`, so a combined code yields `"HIGH : LOW"`.
4. An unrecognised code at either level falls through to `UNKNOWN ERROR CODE (XXXX)`.

**Where the strings come from**

The `switch` bodies are between `/* Begin Auto-Generated Code. */` and the end of the function. They are written by `scripts/generate_errors.pl`, which:

- scans `include/mbedtls/*.h` for `#define MBEDTLS_ERR_<X> -0x....`
- takes the description from a doxygen comment before the define (`/** ... */`) or after it (`/*!< ... */`), but not both, and not neither
- derives the module name from the prefix (`MBEDTLS_ERR_AES_...` gives `AES`)
- sorts each code into the low-level or high-level list, guarded by the module's `MBEDTLS_<MODULE>_C` macro
- writes `library/error.c` from the template `scripts/data_files/error.fmt`

It is run by the `library/Makefile` rule and by a CMake custom command. `tests/scripts/check-generated-files.sh` regenerates the file and fails CI if it differs from the committed copy.

**What a contributor has to do to add one**

1. Add the define to the module's header, for example `include/mbedtls/aes.h`. Use an unused value in the module's range, with a negative hex value. The script does not check ranges, but duplicate values are a fatal error.
2. Write the description as a doxygen comment, either before the define or after it with `/*!<`, and do not use `\name` in the before-comment because the script discards it. The text becomes the user-visible string.
3. If the module prefix is new, add it to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`. Otherwise the script exits with `Do not know how to handle`. If its guard macro is not `MBEDTLS_<MODULE>_C`, add a `$define_name` mapping as well.
4. Regenerate with `scripts/generate_errors.pl` (or `make` in `library/`) and commit the regenerated `library/error.c`. Do not hand-edit it.
5. Run `tests/scripts/check-generated-files.sh` through the project's own test entry point, and add a case to `tests/suites/test_suite_error.data`, which exists but whose format I did not read.

**What I did not verify:** I read the generator script and the lookup functions. I did not run the generator or the tests, and I did not check the range convention beyond what the header comment at `include/mbedtls/error.h:21` says.