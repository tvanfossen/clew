A negative return like `-0x3880` becomes text in `mbedtls_strerror()` (`library/error.c:792`), which splits the code into a high-level part and a low-level part and looks up each in its own generated switch. Adding a new string means adding a header `#define` and regenerating `error.c`, not editing it by hand.

**Runtime path**

```
caller: ret = -0x3880  (MBEDTLS_ERR_PK_BUFFER_TOO_SMALL)
  │
  mbedtls_strerror(ret, buf, buflen)            error.c:792
  ├─ buflen == 0 → return; memset(buf, 0)
  ├─ ret = -ret                                  (sign dropped)
  ├─ if (ret & 0xFF80):                          high part present
  │     mbedtls_high_level_strerr(ret)          error.c:174
  │       switch (ret & 0xFF80) → "PK - The output buffer is too small"
  │     (NULL → "UNKNOWN ERROR CODE (xxxx)")
  │     if high part is SSL fatal alert → return early (no low-level text)
  ├─ use_ret = ret & ~0xFF80; if 0 → done
  ├─ if high text exists: append " : "            (needs ≥5 bytes free)
  └─ mbedtls_low_level_strerr(ret)              error.c:537
        switch (ret & ~0xFF80) → "AES - Invalid key length", etc.
        (NULL → "UNKNOWN ERROR CODE (xxxx)")
```

- **Split by bit mask.** The high-level part is `code & 0xFF80` and the low-level part is `code & ~0xFF80`, so low-level codes must fit in 0x01–0x7F. `MBEDTLS_ERR_PK_BUFFER_TOO_SMALL` is `-0x3880`, which is entirely high-level, so it gets only the first string.
- **Two tables.** Both are `switch` statements over `-(MBEDTLS_ERR_…)` cases, grouped by module and wrapped in `#if defined(MBEDTLS_<MOD>_C)`. Unknown codes fall back to `UNKNOWN ERROR CODE (%04X)`.
- **Dummy build.** When `MBEDTLS_ERROR_C` is off, the second definition at `error.c:867` writes an empty string.

**Where the tables come from**

`library/error.c` is generated, and its "Auto-Generated Code" blocks must not be edited by hand. `scripts/generate_errors.pl` builds it from `scripts/data_files/error.fmt` plus every `include/mbedtls/*.h`. It:

- picks up each `#define MBEDTLS_ERR_X -0x…` together with its doxygen comment (`/** … */` before, or `/*!< … */` after; exactly one is required);
- takes the module name from the prefix (`MBEDTLS_ERR_PK_…` → `PK`) and sorts it into the low-level or high-level list at the top of the script;
- emits the `case` and the `#if` guards, and the `#include` for each header.

**What a contributor does to add one**

1. Pick an unused value in the module's header under `include/mbedtls/`, for example `#define MBEDTLS_ERR_PK_FOO -0x38XX`, with a single doxygen description. The script dies on duplicate values across all headers.
2. If the code is a new module, add it to `@low_level_modules` or `@high_level_modules` in `generate_errors.pl`. An unlisted module makes the script exit with "Do not know how to handle".
3. Regenerate through the build, not by hand. `library/Makefile` has a rule for `error.c` (line 355), and `library/CMakeLists.txt` has the same at line 136. `scripts/make_generated_files.bat` covers Windows.
4. Commit the regenerated `library/error.c` together with the header. `tests/scripts/check-generated-files.sh` runs the generator and fails when the committed file is stale.

I did not verify the test-suite side, such as whether `tests/suites` has a case that exercises each code's string. Check that before relying on it. I also did not open `docs/` for any contributor guidance beyond the generator itself.