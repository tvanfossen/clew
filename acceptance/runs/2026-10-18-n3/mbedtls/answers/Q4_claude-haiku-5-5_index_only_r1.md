The translation lives in `library/error.c`, and the strings are not written by hand in the function that returns them. It takes a negative return code and produces a string in three steps.

**1. Entry point: `mbedtls_strerror(int ret, char *buf, size_t buflen)`** (`library/error.c:792`, declared in `include/mbedtls/error.h:165`)

- If `buflen` is 0 it returns. Otherwise it zeroes `buf`.
- It negates `ret` so the code is positive, then splits it with masks.
- The high-level part is `ret & 0xFF80`. The low-level part is `ret & ~0xFF80`.
- It writes the high-level description first. If the high-level part is the fatal-alert code under `MBEDTLS_SSL_TLS_C`, it returns there and skips the low-level part.
- If there is a low-level part, it appends `" : "` and then the low-level description. An unknown code becomes `UNKNOWN ERROR CODE (%04X)`.

**2. Table lookups**

- `mbedtls_high_level_strerr` (`library/error.c:174`) switches on the high-level bits. Each case is guarded by a module's `#if defined(MBEDTLS_xxx_C)`, for example `CIPHER`, `DHM`, `ECP`, `PK`, `PKCS7`, and `RSA`. Each returns a string such as `"ECP - Invalid private or public key"`.
- `mbedtls_low_level_strerr` (`library/error.c:537`) does the same for the low-level bits. It covers modules such as `AES`, `ASN1`, `BIGNUM`, `CCM`, `ENTROPY`, `ERROR`, `NET`, and `PLATFORM`.
- Both tables sit between `/* Begin Auto-Generated Code. */` markers.

**Flow**

```
caller: ret = -0x2F80 (say)
   │
mbedtls_strerror
   ├─ ret = -ret                       (make positive)
   ├─ high = ret & 0xFF80 ─► mbedtls_high_level_strerr ─► "ECP - ..."
   │     └─ fatal SSL alert? return
   ├─ low  = ret & ~0xFF80 ─► mbedtls_low_level_strerr ─► "... - ..."
   └─ buf = "high : low"
```

The index contains two `mbedtls_strerror` definitions, at lines 792 and 867. I did not confirm from the index which one is the stub used when `MBEDTLS_ERROR_C` is off.

**Adding a new string**

The index shows that the code is in generated blocks, so the supported route is probably to regenerate the tables rather than edit them by hand. I could not confirm that from the index: the generator script is not indexed, and the name `generate_errors` returns nothing in symbols or prose. The likely steps are:

1. Define the new code as a `MBEDTLS_ERR_<MODULE>_<NAME>` macro in the module's public header. `MBEDTLS_ERR_ERROR_GENERIC_ERROR` (`include/mbedtls/error.h:98`) is an example of the form.
2. Choose its bits. High-level codes need to fit under the `0xFF80` mask, and low-level codes need to fit in the low 7 bits. A new code that sets bits outside its half of the mask will be translated wrongly.
3. Regenerate `error.c` with the repo's generator, so the case and string land between the auto-generated markers. Check the generator's own docs or `scripts/` for the exact command.
4. Keep the `#if defined(MBEDTLS_xxx_C)` guard that matches the module, so the string only compiles when the module does.
5. Add a `ChangeLog.d` entry if the repo's convention requires it.

Steps 3 and 5 are the parts I could not verify in the index. Check them against the repo before relying on them.