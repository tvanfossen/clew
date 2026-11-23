The string comes from `mbedtls_strerror()` in `library/error.c`. The lookup tables in that file are generated from the public headers, so a contributor adds a code by editing a header and regenerating, not by editing `error.c`.

**Runtime path**

```
caller: ret = mbedtls_xxx(...)   // ret < 0
   │
   ▼
mbedtls_strerror(ret, buf, buflen)           library/error.c:792
   1. buflen == 0 → return; else memset(buf, 0)
   2. ret = -ret                              // make it positive
   3. high = ret & 0xFF80                     // module/category bits
        → mbedtls_high_level_strerr(ret)      // switch over ~0x80 codes
        → write "CIPHER - Authentication failed …" (or "UNKNOWN ERROR CODE (%04X)")
        → if high == SSL fatal alert: return  // skip low-level part
   4. low = ret & ~0xFF80                     // specific reason bits
        → if low == 0: return
        → if buf already has text: append " : "
        → mbedtls_low_level_strerr(ret)       // switch over low codes
        → write "AES - Invalid key length" (or "UNKNOWN ERROR CODE (%04X)")
```

So a code such as `-0x0020` (`MBEDTLS_ERR_AES_INVALID_KEY_LENGTH`, defined in `include/mbedtls/aes.h:44`) resolves through the low-level switch to `"AES - Invalid key length"`. A code that combines a high-level and a low-level part produces a concatenated string such as `"X : Y"`. The result is always NUL-terminated and truncated to `buflen`.

If `MBEDTLS_ERROR_C` is off, the `#else` branch at `error.c:867` compiles a stub that writes an empty string.

**Where the tables come from**

`library/error.c` is generated. Its header says so, and `scripts/generate_errors.pl` writes it from:

- the template `scripts/data_files/error.fmt`
- every `include/mbedtls/*.h` that contains `#define MBEDTLS_ERR_... -0x...`

The generator's regex accepts a doxygen comment either before the define (`/** ... */`) or after it (`/**< ... */`), but not both and not neither. It then:

- dies on a duplicate numeric code
- sorts each code into a low-level or high-level table using hard-coded module lists (`@low_level_modules` and `@high_level_modules` near the top of the script)
- emits `#if defined(MBEDTLS_<MOD>_C)` guards and `case -(NAME): return "MOD - description";` lines

Regeneration runs from `library/Makefile:355-360` and the CMake equivalent whenever a header changes. `tests/scripts/check-generated-files.sh:135` regenerates and diffs, so a hand-edited `error.c` fails CI.

**To add a new error string**

1. In the module's public header, add `#define MBEDTLS_ERR_<MOD>_<NAME> -0x<value>` with a single doxygen description on the line before or after. Pick an unused value in the module's range, and keep the code within the low-level (`< 0x80`) or high-level (`0xFF80` mask) range the module already uses.
2. If the module is new to the error system, add its name to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`. Otherwise the script exits with `Do not know how to handle`.
3. Regenerate with `make -C library error.c` or the CMake target, or run `scripts/generate_errors.pl` from the repo root. Commit the regenerated `library/error.c` along with the header change.
4. Run the check through pre-commit or the repo's CI scripts, not by running the generator alone.

I only read the code and did not run the generator or the check script, so the regeneration step and the exact make target are verified by reading, not by running them.