**The path from integer to string**

1. The caller passes the negative return value and a buffer to `mbedtls_strerror(ret, buf, buflen)` (`library/error.c:792`, declared in `include/mbedtls/error.h:165`). The function returns `void`. It zeroes the buffer, returns early if `buflen` is 0, and truncates to fit.
2. It takes the magnitude (`ret = -ret`) and splits it with two masks. Bits in `0xFF80` are the high-level module, and bits in `~0xFF80` are the low-level code.
3. The high-level part goes to `mbedtls_high_level_strerr()` (`error.c:174`). The low-level part goes to `mbedtls_low_level_strerr()` (`error.c:537`). Each is a `switch` over the code. Each `case` returns a string of the form `"MODULE - description"`.
4. If both parts are present, they are joined as `"HIGH : LOW"`. The one exception is a fatal SSL alert, where the function returns after the high-level text and skips the low-level part.
5. A code with no matching `case` gives `"UNKNOWN ERROR CODE (XXXX)"`.

```
caller ── mbedtls_strerror(ret, buf, n)
             │ ret = -ret; split mask 0xFF80
     ┌───────┴────────────────┐
mbedtls_high_level_strerr   mbedtls_low_level_strerr
  (switch on high bits)       (switch on low bits)
     └───────┬────────────────┘
      "HIGH : LOW" into buf (truncated to buflen)
```

The `switch` bodies are between `/* Begin Auto-Generated Code. */` markers and are guarded by `#if defined(MBEDTLS_<MODULE>_C)`, so a module that is compiled out contributes no strings.

**Where the strings come from**

`library/error.c` is generated, not hand-written. `scripts/generate_errors.pl` scans `include/mbedtls/*.h` for `#define MBEDTLS_ERR_* -0xNNNN` lines and writes one `case` per code, using the Doxygen comment next to the define as the description. It is run by `library/Makefile:355-360` and by the CMake `GEN_FILES` rule in `library/CMakeLists.txt:139`. `library/error.c` is also tracked in git.

**What a contributor has to do to add a new error code**

1. Add the define to the module's header, for example `include/mbedtls/aes.h`, in an existing or new range. The value must be written as `-0xNNNN` with a leading minus and hex literal, because the script's regex requires it.
2. Give it exactly one Doxygen description, either a `/** ... */` before the define or a `/**< ... */` after it. The script dies if it has neither or both.
3. If the code belongs to a new module, add the module name to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`. An unknown module makes the script exit with "Do not know how to handle". Also add the header to the include mapping if its name does not follow the default.
4. Regenerate with `make` in `library/` or the CMake build, not by hand. The generator rejects duplicate values, and it fails if a header defines codes but is not included in the generator's list.
5. Commit the header change and the regenerated `library/error.c` together. Hand edits to `error.c` will be overwritten on the next build.
6. Per the repo's rules, add or update a test that asserts the new string. I did not check which test suite covers `mbedtls_strerror` output, so I cannot point to the exact place.

I did not run the generator or the build, so the steps above come from reading the script and build files.