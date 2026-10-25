**Short answer:** an mbedtls error is a negative int whose bits are split into a high-level module part and a low-level part. `mbedtls_strerror()` flips the sign, masks the two parts apart, looks each up in a `switch` in `library/error.c`, and concatenates the strings. To add a new one, you add the error macro to the owning module's header and let the generated `switch` cases in `error.c` pick it up. I did not find the generator script or any contributor doc for that step in the index, so treat the second part as partly inferred.

**Walk-through**

1. **Encoding.** Each code is a negative int. The top bits (mask `0xFF80`) identify the module, and the low 7 bits (`~0xFF80`) identify the specific error. Example: `MBEDTLS_ERR_ERROR_GENERIC_ERROR` is `-0x0001` (low-level, no module bits), and `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE` is `-0x7780` (high-level). Combining the two parts is `mbedtls_error_add()` in `include/mbedtls/error.h:142`, which returns `high + low`.

2. **Entry point.** `mbedtls_strerror(int ret, char *buf, size_t buflen)` is in `library/error.c:792`. It returns `void`, writes into the caller's buffer, and is gated on `MBEDTLS_ERROR_C`. It does the following:
   - Returns immediately if `buflen == 0`, and zeroes the buffer otherwise.
   - Negates a negative `ret`.
   - If any high-level bits are set, calls `mbedtls_high_level_strerr()` and writes its text. If that returns NULL, it writes `UNKNOWN ERROR CODE (%04X)`.
   - Returns early if the high-level code is `SSL_FATAL_ALERT_MESSAGE`, because the low-level part is not meaningful for that case.
   - If the low-level part is non-zero, appends `" : "` (only if there is room, at least 5 bytes) and calls `mbedtls_low_level_strerr()` for the second half, with the same unknown-code fallback.

3. **Lookup tables.** `mbedtls_high_level_strerr()` (`error.c:174`) and `mbedtls_low_level_strerr()` (`error.c:537`) are each a large `switch` over the masked value. Each `case` is wrapped in its module's `#if defined(MBEDTLS_xxx_C)`, and the strings have the form `"MODULE - description"`, for example `"ECP - Memory allocation failed"`. The switches are marked `/* Begin Auto-Generated Code. */`.

4. **Result.** For a combined code the caller gets something like `"ECP - ... : BIGNUM - ..."`. If `buflen` is too small, the output is truncated but always NUL-terminated.

**To add a new error**

1. Define the new `MBEDTLS_ERR_<MODULE>_<NAME>` macro in the owning module's public header (`include/mbedtls/<module>.h`), using the module's allocated range. The range rules are in the header.
2. Add its `case` and description string to the generated section of `error.c`. Because that section is auto-generated, the change should go through the generator, not a hand edit. I could not confirm which script produces `error.c`. The index has no symbol for it, and the `.pl`/`.py` scripts in `scripts/` are only partly visible. Check `scripts/` and the README's "Generated source files" section before editing.
3. Keep the description short and in the same `MODULE - text` style. Per the `strerror` docs, the string is what users see in logs and in `programs/util/strerror.c`.

**Caveats**

- `mbedtls_strerror` has two definitions in `error.c` (lines 792 and 867). The second is probably the stub used when `MBEDTLS_ERROR_STRERROR_DUMMY` is set (`configs/config-symmetric-only.h:26`), but I did not verify that.
- The index has no prose describing the generator workflow, so the contributor steps above are based on the code layout alone.