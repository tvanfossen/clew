Short version: `mbedtls_strerror()` does not look anything up in a runtime table. The string lookup code in `library/error.c` is generated from the `MBEDTLS_ERR_*` defines in `include/mbedtls/*.h`, so a new message means adding a header define and regenerating.

**Runtime path** (`library/error.c:792`)

```
caller: int ret = -0x0020
  │
  ▼ mbedtls_strerror(ret, buf, buflen)
  │   • buflen == 0 → return
  │   • memset(buf, 0)
  │   • ret = -ret                       (sign dropped; value is now 0x0020)
  │
  ├─ ret & 0xFF80 ? ──yes──▶ mbedtls_high_level_strerr(ret)
  │                            • switch on (ret & 0xFF80)
  │                            • "CIPHER - …", "ECP - …", "X509 - …" …
  │                            • NULL → "UNKNOWN ERROR CODE (%04X)"
  │   • if high-level is SSL FATAL_ALERT_MESSAGE → return now (no low-level part)
  │
  ├─ use_ret = ret & ~0xFF80 ; == 0 ? → return (high-level text only)
  │
  ├─ buf already has text? → append " : "
  │
  ▼ mbedtls_low_level_strerr(ret)
      • switch on (ret & ~0xFF80)
      • "AES - Invalid key length", "ASN1 - …", …
      • NULL → "UNKNOWN ERROR CODE (%04X)"
```

- **Two halves.** Codes are split by mask. Bits in `0xFF80` are the high-level module part (`CIPHER`, `DHM`, `ECP`, `MD`, `PEM`, `PK`, `PKCS12`, `PKCS5`, `RSA`, `SSL`, `X509`, `PKCS7`). The remaining low bits are the low-level part (`AES`, `ASN1`, `BIGNUM`, `MD5`, `SHA256`, …). Output is e.g. `"X509 - … : ASN1 - Out of data…"`.
- **Output is always terminated** and truncated if `buflen` is small.
- **Unknown codes** fall through to `UNKNOWN ERROR CODE (xxxx)` rather than failing.
- **Compile gating.** Both functions are wrapped in `MBEDTLS_ERROR_C` (and `MBEDTLS_ERROR_STRERROR_DUMMY` supplies a stub that just empties the buffer).

**How the table gets built**

1. Each error is a define in a public header, e.g. `include/mbedtls/aes.h:44`:
   ```c
   /** Invalid key length. */
   #define MBEDTLS_ERR_AES_INVALID_KEY_LENGTH   -0x0020
   ```
2. `scripts/generate_errors.pl` (Perl) globs `include/mbedtls/*.h`, applies a regex that requires a doxygen description (before or after the define) and a **negative hex** value, and emits one `case -(NAME): return "MODULE - description";` per code. It groups cases under `#if defined(MBEDTLS_<MOD>_C)` blocks and adds the matching `#include` lines.
3. The template is `scripts/data_files/error.fmt`. The output is the committed file `library/error.c`.
4. `library/Makefile:355-360` regenerates `error.c` when headers change. `scripts/make_generated_files.bat` does the same on Windows. `tests/scripts/check-generated-files.sh:135` fails CI if the committed `error.c` is out of date.

**What a contributor has to do to add a new code**

1. **Pick the value and define it** in the module's header, with a `-0x....` hex literal and a doxygen comment. Use an unused value in the module's range. Decimal values are silently ignored by the regex.
2. **Make sure the module is known to the generator.** If the prefix is new, add it to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl:31-38`. An unknown module prints "Do not know how to handle" and exits 1. Also add the module's `define_name` and include-name mapping if it has special naming (see the `$define_name`/`$include_name` fix-ups around lines 120-130).
3. **Header must be included by the generator's scan.** A header that defines codes but isn't picked up in `@necessary_include_files` triggers "has not been included!" and a non-zero exit.
4. **Regenerate** `library/error.c` (via `make` in `library/` or `perl scripts/generate_errors.pl` from the repo root). Do not hand-edit `error.c`; the next regeneration overwrites it and the generated-files check fails.
5. **Add a changelog entry** under `ChangeLog.d/` (see `ChangeLog.d/00README.md`). A new error code is user-visible, so it belongs in a category like "Features" or "API changes".
6. **Run the check** through pre-commit (`.venv/bin/pre-commit run --all-files`) per the house rules, not the scripts directly.

I haven't run the generator or the check script in this session, so the exact invocation in step 4 comes from the Makefile and CMake rules I read, not from a test run.