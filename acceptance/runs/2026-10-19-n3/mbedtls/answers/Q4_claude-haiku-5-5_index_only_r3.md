A negative code becomes text in `mbedtls_strerror()` in `library/error.c`. The declaration is in `include/mbedtls/error.h:165`, and the body runs from `error.c:792` to `:860`. The index doesn't show a generator script, so the steps for adding a code are only partly confirmed.

**Translation path**

1. The caller passes the return value, a buffer and its length. If `buflen` is 0 it returns; otherwise it zeroes the buffer.
2. The sign is dropped (`ret = -ret`), so `-0x000D` and `0x000D` are handled the same way.
3. **High-level part:** `ret & 0xFF80` goes to `mbedtls_high_level_strerr()` (`error.c:174`). That is a `switch` over per-module codes, each case under its module's `#if defined(MBEDTLS_xxx_C)`. A match returns a string such as `"CIPHER - Authentication failed (for AEAD modes)"`. An unknown value formats as `UNKNOWN ERROR CODE (%04X)`.
4. **Early exit:** if the high-level part is the SSL fatal-alert wrapper (`MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`, `-0x7780`, `include/mbedtls/ssl.h:76`), it stops there and does not translate the low-level part.
5. **Low-level part:** `ret & ~0xFF80` goes to `mbedtls_low_level_strerr()` (`error.c:537`), another `switch` with the same module guards. If a high-level string was already written, it appends `" : "` and continues into the rest of the buffer.
6. **Truncation:** if fewer than 5 bytes remain, the append is skipped. Each `snprintf` keeps the buffer null-terminated.

Example: `MBEDTLS_ERR_CCM_BAD_INPUT` is `-0x000D`. It has no high-level bits, so the output is just `"CCM - Bad input parameters to the function"`.

When `MBEDTLS_ERROR_C` is off, `error.c` compiles a different `mbedtls_strerror` stub (around line 867). I inferred that from the gate ranges; I did not read its body.

**Adding a new code**

- Define the `MBEDTLS_ERR_<MODULE>_<NAME>` macro in the module's public header, with a value that doesn't collide with existing codes in that module's range. I did not verify the range rules.
- Add a `case` for it in `mbedtls_high_level_strerr` or `mbedtls_low_level_strerr`, inside the block for that module, under the same `#if` guard the module uses. The string format is `"MODULE - description"`.
- Don't hand-edit those blocks blindly. Both switches are marked `/* Begin Auto-Generated Code */`, and the README has a "Generated source files" section that presumably explains the generator. I could not read that section or find the generator through the index (`generate_errors` returned nothing, and `.pl` files aren't indexed), so check it before editing.
- Verify with `programs/util/strerror.c`, which takes an error code (decimal or `0x`/`-0x`) and prints its string.
- Add a `ChangeLog.d` entry if the repo's convention requires one. The directory is indexed, but I did not check its rules.