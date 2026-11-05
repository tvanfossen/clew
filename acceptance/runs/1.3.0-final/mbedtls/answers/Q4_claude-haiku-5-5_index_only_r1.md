**How a negative code becomes a string**

1. **Caller passes the code.** `mbedtls_strerror(int ret, char *buf, size_t buflen)` (`library/error.c:792`) is the entry point. It returns nothing and writes into `buf`. If `buflen` is 0 it returns immediately, and it zeroes the buffer first.
2. **Sign is dropped.** `ret` is negated if negative, so the lookup works on the positive magnitude.
3. **Code is split into two bands.** Mbed TLS packs each error as a module (high-level) part and a specific (low-level) part:
   - High-level: `ret & 0xFF80` (the module identity, e.g. CIPHER, DHM, ECP).
   - Low-level: `ret & ~0xFF80` (the specific reason within the module).
4. **High-level lookup.** If the high band is non-zero, `mbedtls_high_level_strerr` (`error.c:174`) runs a `switch` over the masked value and returns a module string. Unknown values fall back to `"UNKNOWN ERROR CODE (%04X)"`. For SSL fatal alerts (`MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`) it returns early and skips the low-level part.
5. **Concatenate.** If both parts exist, it writes `" : "` and appends the low-level text. It bails out if fewer than 5 bytes remain.
6. **Low-level lookup.** `mbedtls_low_level_strerr` (`error.c:537`) switches on the low band and returns the specific reason, e.g. `"CIPHER - Authentication failed (for AEAD modes)"` style strings. Unknown values get the same `UNKNOWN ERROR CODE` fallback.

Example shape: `-0x6080` (`MBEDTLS_ERR_CIPHER_FEATURE_UNAVAILABLE`, from `include/mbedtls/cipher.h`) resolves through the CIPHER module case in the high-level switch and the specific case in the low-level switch. The exact output string for a combined code is built by the two functions above, so read them rather than trusting my paraphrase.

Both switch tables are generated. `library/error.c` is the output of `scripts/generate_errors.pl`, run by a CMake custom command in `library/CMakeLists.txt:134`. That command takes `include/mbedtls` and `scripts/data_files`, and depends on the error headers and `scripts/data_files/error.fmt`. Each generated `case` is wrapped in its module's `#if defined(MBEDTLS_xxx_C)`, so a disabled module drops out of the table.

Two things I could not settle from the index:
- The generator's body and `error.fmt` are not indexed (`scripts/generate_errors.pl` shows zero symbols, and `.fmt` files are excluded). So I cannot say exactly which header comment becomes the description text, or how the `"CIPHER - "` prefix is derived.
- `mbedtls_strerror` has a second definition at `error.c:867`, gated on `MBEDTLS_ERROR_STRERROR_DUMMY`. I did not trace which build selects which one.

**Adding a new one**

1. Add the `#define MBEDTLS_ERR_<MODULE>_<REASON> -0xNNNN` in the module's public header (e.g. `include/mbedtls/<module>.h`). Pick a value in that module's high band, and do not collide with an existing code.
2. Document the code's meaning in the header comment. The generator reads it, so the comment is the description source. Confirm the exact format in `scripts/generate_errors.pl` before relying on it.
3. Do not edit `library/error.c`. It is regenerated at build time. Rebuild and check that the new `case` appears in both switches under the right `#if`.
4. Add a RED test first: call `mbedtls_strerror` on the new code and assert the expected string, then make it pass by building. Also check the module's gate, since a module-only build must still compile.
5. Check whether the repo's ChangeLog convention expects an entry (there is a `ChangeLog.d` directory). I did not verify the convention from the index.