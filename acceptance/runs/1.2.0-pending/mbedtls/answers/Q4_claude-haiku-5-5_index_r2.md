The negative code is turned into text by a generated lookup table in `library/error.c`, not by hand-written code. A contributor adds a string by adding a documented `MBEDTLS_ERR_*` define to a public header and regenerating that file.

**Runtime path**

1. A caller passes the negative `ret` to `mbedtls_strerror(int ret, char *buf, size_t buflen)` (`library/error.c:792`, declared in `include/mbedtls/error.h:165`). It clears `buf`, then takes the absolute value, since codes are stored negated.
2. The high-level part is `ret & 0xFF80`. If it is nonzero, `mbedtls_high_level_strerr()` (`library/error.c:174`) looks it up. A miss yields `UNKNOWN ERROR CODE (%04X)`.
   - If the high-level code is `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`, the function returns early, so the low-level part is not translated.
3. The low-level part is `ret & ~0xFF80`. If it is nonzero, `mbedtls_low_level_strerr()` (`library/error.c:537`) looks it up. If both parts are present, the strings are joined with `" : "`. The buffer is always null-terminated and silently truncated when full.
4. Each lookup is a `switch` over `case -(MBEDTLS_ERR_X):` returning a `"MODULE - description"` literal. Those cases sit inside `#if defined(MBEDTLS_X_C)` blocks, so a code whose module is compiled out is not in the table.
5. Without `MBEDTLS_ERROR_C` (and `MBEDTLS_ERROR_STRERROR_DUMMY`), the function is a stub that writes an empty string.

**Where the table comes from**

`library/error.c` is generated from `scripts/data_files/error.fmt` by `scripts/generate_errors.pl`. The Makefile rule is at `library/Makefile:355`, and CMake runs the same script from `library/CMakeLists.txt:139`. `tests/scripts/check-generated-files.sh:135` regenerates the file and checks it against the committed copy.

The script scans every `include/mbedtls/*.h` for this pattern:

```c
/** Invalid key length. */
#define MBEDTLS_ERR_AES_INVALID_KEY_LENGTH                -0x0020
```

- The value must be a negative hex literal (`-0x....`).
- It needs exactly one doxygen description, either a `/** */` before the define or a `/*!< */` after it. Having neither or both is a fatal error.
- The module is the segment after `MBEDTLS_ERR_` (`AES` above). `MPI`, `CTR` and `HMAC` are remapped to `BIGNUM`, `CTR_DRBG` and `HMAC_DRBG`.
- The module must appear in `@low_level_modules` or `@high_level_modules` at the top of the script. Otherwise the script prints `Do not know how to handle` and exits 1.
- Duplicate values are fatal.

**What a contributor does to add one**

1. Add a `#define MBEDTLS_ERR_<MODULE>_<NAME>  -0x00XX` in the module's header, in its range, with a doxygen description on the line before or after. Keep the value inside the module's range and unused.
2. If the module is new, add it to the correct list in `generate_errors.pl` (low-level or high-level, which decides which lookup function it lands in). Also add a header in `include/mbedtls/` named after the module, since the generator derives the include name from it.
3. Regenerate through the build, `make` in `library/` or the CMake target, not by running the script by hand. Then commit the regenerated `library/error.c`, since the check script fails if it is stale.
4. Run the gate with `.venv/bin/pre-commit run --all-files` (per the repo's own convention) and any tests covering the new code.

I did not run the generator or the build here, so the regeneration step is from reading the Makefile and script rather than an observed run. Also, `mbedtls_strerror` negates `ret` before masking, which is undefined for `INT_MIN`; that is outside the question but worth knowing.