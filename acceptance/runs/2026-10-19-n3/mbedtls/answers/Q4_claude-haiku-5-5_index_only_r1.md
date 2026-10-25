**How a negative code becomes a string**

The entry point is `mbedtls_strerror(int ret, char *buf, size_t buflen)` in `library/error.c:792`, declared in `include/mbedtls/error.h:165`. It:

1. Returns immediately if `buflen == 0`, then zeroes `buf`.
2. Negates `ret` so the rest of the logic works on positive values.
3. Masks out the high part with `0xFF80`. If it is nonzero, it calls `mbedtls_high_level_strerr()` (`error.c:174`), which switches on that masked value and returns a string such as `"CIPHER - Authentication failed (for AEAD modes)"`. If the module has no entry, it writes `UNKNOWN ERROR CODE (XXXX)`. For SSL fatal alerts it returns early and skips the low-level part.
4. Masks the low part with `~0xFF80` and returns if that is zero. Otherwise it appends `" : "` to the buffer when the high part was written, provided at least 5 bytes remain. It then calls `mbedtls_low_level_strerr()` (`error.c:537`), which switches on the low bits and returns strings such as `"AES - Invalid key length"`, with the same `UNKNOWN ERROR CODE` fallback.

```
ret (-0x6300)
  │ negate, zero buf
  ├─ high = ret & 0xFF80 ──► mbedtls_high_level_strerr ──► "CIPHER - ..."
  │                                                         │
  └─ low  = ret & ~0xFF80 ─► mbedtls_low_level_strerr ──► " : " + "AES - ..."
                                                            ▼
                                             buf (truncated, NUL-terminated)
```

Both lookup functions are large `switch` blocks that open with `/* Begin Auto-Generated Code. */` and group cases under `#if defined(MBEDTLS_<MODULE>_C)`. Each case is `case -(MBEDTLS_ERR_...)` returning a `"MODULE - description"` string.

When `MBEDTLS_ERROR_C` is off, `error.c` is gated (around lines 12–14 and 862–878) on `MBEDTLS_ERROR_STRERROR_DUMMY`, which is defined in `configs/config-symmetric-only.h:26` and `include/mbedtls/mbedtls_config.h:1170`. A second `mbedtls_strerror` candidate at `error.c:867` is probably the dummy variant. I did not read its body.

**Adding a new error string**

1. **Define the code** in the module's public header, using the `MBEDTLS_ERR_<MODULE>_<NAME>` pattern. For example, `MBEDTLS_ERR_CIPHER_AUTH_FAILED` is `-0x6300` in `include/mbedtls/cipher.h:48`. Choose an unused value in the module's range. I could not confirm how those ranges are allocated.
2. **Add the description string.** The `switch` blocks in `error.c` are marked auto-generated, so the string should come from the generator, not a hand edit. The index does not show the generator script: `scripts/` `.pl` files are not indexed, and a prose search for `generate_errors` returned nothing. Find that script in the repo before editing.
3. **Regenerate and build** through the project's normal path (pre-commit and the test tasks), not by running tools directly.
4. **Add a changelog entry** under `ChangeLog.d/` if the change is user-visible. `ChangeLog.d/00README.md` says to write one for user-visible changes. A new error string probably qualifies, but that is your call.

I could not verify step 2's generator or the value-range rule, because I only had the index and no shell or file reads.