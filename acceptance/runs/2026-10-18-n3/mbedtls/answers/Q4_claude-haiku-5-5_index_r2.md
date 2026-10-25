The caller's integer goes through `mbedtls_strerror()` in `library/error.c`, which splits it into two halves and looks each half up in a generated `switch`. Adding a new string means adding a `#define` in a public header with a doc comment, then regenerating `error.c`.

**Translation path**

1. **Entry point.** `mbedtls_strerror(int ret, char *buf, size_t buflen)` (`library/error.c:792`) is the public function. It returns nothing. It zeroes `buf`, takes the absolute value of `ret`, and writes the text into the caller's buffer, truncating if needed.
2. **Split by bit mask.** The code is partitioned by bits:
   - High-level part: `ret & 0xFF80`. This identifies the module, such as SSL, X509 or CIPHER.
   - Low-level part: `ret & ~0xFF80`. This identifies the specific error within that module, or the low-level primitive, such as AES or ASN1.
3. **High-level lookup.** If the high-level part is nonzero, `mbedtls_high_level_strerr()` (`error.c:174`) returns a string like `"CIPHER - Bad input parameters"`. If it returns NULL, the buffer gets `UNKNOWN ERROR CODE (XXXX)`. One exception: a fatal SSL alert (`MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`) returns early and skips the low-level part.
4. **Separator.** If both parts exist, `" : "` is appended and the low-level text follows.
5. **Low-level lookup.** `mbedtls_low_level_strerr()` (`error.c:537`) does the same kind of switch for the low bits. Unknown codes produce the same `UNKNOWN ERROR CODE` fallback.

A caller such as `ret = MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE` reads as a high-level SSL string alone, while a value that combines a module code with a primitive code produces the `HIGH : LOW` form.

There is a second `mbedtls_strerror` definition at `error.c:867`. It is compiled under `MBEDTLS_ERROR_STRERROR_DUMMY` for configs without `MBEDTLS_ERROR_C` and is a stub, so the real lookup only exists when `MBEDTLS_ERROR_C` is enabled.

**Where the switch tables come from**

`library/error.c` is generated. Do not hand-edit it. `scripts/generate_errors.pl` builds it from:
- every `include/mbedtls/*.h` file, by regex-matching `#define MBEDTLS_ERR_xxx -0xNNNN` lines with a doxygen description, and
- the template `scripts/data_files/error.fmt`.

The generator groups codes by module prefix, using the module lists at the top of the script:
- `@low_level_modules`: AES, ASN1, BASE64, BIGNUM, ... SHA256, ... THREADING
- `@high_level_modules`: CIPHER, DHM, ECP, MD, PEM, PK, PKCS12, PKCS5, RSA, SSL, X509, PKCS7

Each group gets its own `#if defined(MBEDTLS_<MODULE>_C)` block, so strings only compile in when their module is enabled. The output contains lines like `case -(MBEDTLS_ERR_AES_INVALID_KEY_LENGTH): return("AES - Invalid key length");`. The description comes from the doxygen comment, and `#include` lines are emitted for each header that defines codes.

**What a contributor has to do to add a new code**

1. **Define the code in the right header.** Put `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....` in the module's header, for example `include/mbedtls/aes.h`, inside the module's existing range. Use the sign and hex form the regex expects, and pick an unused value.
2. **Add exactly one description.** Use either a `/** ... */` or `/*!< ... */` comment before or after the define, but not both. The generator dies if the description is missing or appears on both sides. Avoid `\name` in the leading comment, since the script discards it.
3. **Pick the group.** If the module prefix is not in `@low_level_modules` or `@high_level_modules`, the generator exits with `Do not know how to handle`. A new module needs a line added to one of those lists, and possibly a `define_name` or `include_name` exception.
4. **Avoid duplicate values.** The generator dies on `Duplicated error code`.
5. **Regenerate.** Run `scripts/generate_errors.pl` from the repo root, or let `library/Makefile` (`error.c` rule) or `library/CMakeLists.txt` do it. `scripts/make_generated_files.bat` covers Windows. Do not commit a hand-edited `error.c`. CI runs `tests/scripts/check-generated-files.sh`, which regenerates `error.c` and fails if it differs.
6. **Test it.** `tests/suites/test_suite_error.function` and `.data` drive `mbedtls_strerror`. I did not read the `.data` entries, so I cannot say whether a new code needs one. Add one if the existing entries follow that pattern.

Things I did not verify: whether the header-only route is the only way to add a code, and the exact contents of the error test data file.