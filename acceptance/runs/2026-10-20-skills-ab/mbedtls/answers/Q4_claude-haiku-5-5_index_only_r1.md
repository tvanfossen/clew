**From a negative return code to a string**

Mbed TLS error codes are negative integers that pack two parts. The high bits (mask `0xFF80`) name the module, and the low bits name the specific error. For example, `MBEDTLS_ERR_CIPHER_BAD_INPUT_DATA` is `-0x6100` (`include/mbedtls/cipher.h:40`), and `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE` is `-0x7780` (`include/mbedtls/ssl.h:76`).

A caller passes the code to `mbedtls_strerror(ret, buf, buflen)` (declared `include/mbedtls/error.h:165`, defined `library/error.c:792`). It runs in this order:

1. If `buflen` is 0, return. Otherwise clear `buf` and negate `ret` to make it positive.
2. If any high bits are set, call `mbedtls_high_level_strerr()` (`library/error.c:174`). It returns a module prefix and description such as `"CIPHER - Authentication failed (for AEAD modes)"`. If there is no match, the buffer gets `UNKNOWN ERROR CODE (xxxx)`.
3. If the high part is the SSL fatal-alert code, return now. The low-level part is not translated for that case.
4. Strip the high bits. If nothing remains, return. The high-level string is the whole message.
5. Otherwise append `" : "` to the buffer, then call `mbedtls_low_level_strerr()` (`library/error.c:537`). It returns a description such as `"AES - Invalid key length"`, or `UNKNOWN ERROR CODE` on a miss. The final string can therefore look like `"<module> - <high> : <module> - <low>"`.

Each `case` in both lookup switches is wrapped in `#if defined(MBEDTLS_<MODULE>_C)`. That means a module that is compiled out has its strings removed. From the code shown, a lookup miss returns NULL and the caller prints `UNKNOWN`. The lookup gating is inferred from the code, and I did not see the default branch.

Only the file-level `#if defined(MBEDTLS_ERROR_C)` gate, not the table gates, applies to `mbedtls_strerror` itself. `MBEDTLS_ERROR_STRERROR_DUMMY` is a config symbol that is referenced in that gate.

**Adding a new code**

1. Define `MBEDTLS_ERR_<MODULE>_<NAME>` in the module's public header as a negative hex value. Use that module's high-bit band and a free low-bit slot. Keep the value inside the module's existing range.
2. Add the description. Both lookup switches are marked `/* Begin Auto-Generated Code. */`, so the case should come from the generator, not a hand edit. Put the case in the same `#if defined(MBEDTLS_<MODULE>_C)` block, and follow the `"MODULE - description"` string convention.
3. Regenerate `error.c` from the generator's input.
4. Changes that add a new error condition for an existing function count as a backwards-compatibility change (`BRANCHES.md`, "Backwards Compatibility for application code"). Document them in the function's docs.

**What I could not verify from the index**

The generator script is not in the index. The `.pl` files are not indexed, and searches for `generate_errors` returned nothing. The exact generator name, its input format, and the changelog convention for new codes must be read from the tree directly.