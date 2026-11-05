**Short answer:** `mbedtls_strerror()` in `library/error.c` splits the code into a module part and a low-level part, and each part is looked up in a generated `switch`. To add a new string, you add the `MBEDTLS_ERR_*` macro in the module's header, then regenerate the switch cases in `error.c` with `scripts/generate_errors.pl`. I did not confirm how that script is invoked or where it gets the description text, so check it before relying on the steps below.

**The path from a negative return to a string**

1. A caller gets `ret` (for example `-0x6100`) and passes it with a buffer to `mbedtls_strerror(int ret, char *buf, size_t buflen)` (`library/error.c:792`, declared in `include/mbedtls/error.h:165`).
2. It returns early if `buflen == 0`, zeroes the buffer, and takes the absolute value of `ret`.
3. **High-level part:** `ret & 0xFF80` selects the module bits. `mbedtls_high_level_strerr()` (`library/error.c:174`) switches on that value and returns a string such as `"CIPHER - Bad input parameters"`. Each case is wrapped in its module's `#if defined(MBEDTLS_xxx_C)`, so modules compiled out of the build have no entries. If no case matches, the buffer gets `UNKNOWN ERROR CODE (XXXX)`.
4. If the module was SSL's fatal-alert code, it returns here and does not translate the low part.
5. **Low-level part:** `ret & ~0xFF80` is the code within the module. `mbedtls_low_level_strerr()` (`library/error.c:537`) switches on it the same way, with the same per-module guards, e.g. `"AES - Invalid key length"`.
6. If both parts are present, the two strings are joined with `" : "`, and the function keeps going while the buffer has room.

The string is truncated to fit `buflen` and is always null-terminated. A typical caller is `programs/test/benchmark.c`'s `PRINT_ERROR`, which calls `mbedtls_strerror(ret, tmp, sizeof(tmp))`.

**What a contributor does to add one**

1. Add the macro to the module's public header (e.g. `include/mbedtls/cipher.h`), with a value in the existing hex scheme. Header values look like `-0x6080` for CIPHER, so the high bits must match that module's range.
2. Regenerate the switch cases in `library/error.c`. The two switch bodies are marked `/* Begin Auto-Generated Code. */`, and the index holds `scripts/generate_errors.pl`. Do not hand-edit that block. Run the generator the way the repo's pre-commit/tasks setup expects.
3. The new entry needs the same `#if defined(MBEDTLS_<MODULE>_C)` guard as its neighbours, or it breaks builds that disable that module.
4. Add a test per the repo's rule that tests are specifications: a case where the new code is returned and its text is checked. I did not find a covering test for `mbedtls_strerror` in the index.

**What I could not settle from the index**

- The index lists a second `mbedtls_strerror` definition at `library/error.c:867`, most likely the `MBEDTLS_ERROR_STRERROR_DUMMY` variant. I did not read it.
- Where the generator takes the description text from (the header comment or a table in the script) is not visible through the index. The script has no indexed symbols.