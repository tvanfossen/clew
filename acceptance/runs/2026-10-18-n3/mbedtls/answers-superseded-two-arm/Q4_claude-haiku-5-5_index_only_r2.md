The index covers the runtime path well. It does not show the generator that produces the lookup tables, so the contributor steps are partly inferred.

**Runtime path: negative int to string**

```
caller: mbedtls_strerror(ret, buf, buflen)        library/error.c:792
  ├─ buflen == 0 → return
  ├─ memset(buf, 0); ret = -ret if negative
  ├─ high = ret & 0xFF80 → mbedtls_high_level_strerr()   error.c:174
  │     NULL → "UNKNOWN ERROR CODE (xxxx)"
  │     SSL fatal alert → return early (no low-level lookup)
  ├─ low = ret & ~0xFF80; low == 0 → return
  ├─ if buf already has text: append " : " (skipped if < 5 bytes left)
  └─ mbedtls_low_level_strerr(ret)                     error.c:537
        switch(low) → "MODULE - description"
        NULL → "UNKNOWN ERROR CODE (xxxx)"
```

1. **Sign:** the function takes the absolute value, since Mbed TLS codes are negative.
2. **Split:** the mask `0xFF80` separates a high-level part (the module, such as CIPHER, DHM, ECP, PK, PKCS7, RSA) from a low-level part (the specific failure within that module).
3. **Lookup:** each part is a `switch` in `library/error.c`. Each case is wrapped in `#if defined(MBEDTLS_<MODULE>_C)`, so a module's strings are compiled out when the module is disabled. The low-level table starts at line 537 and covers modules such as AES, ASN1, BIGNUM, CTR_DRBG, ENTROPY, ERROR, NET, and LMS. Strings take the form `"MODULE - description"`.
4. **Combining:** the result is the high-level text, then `" : "`, then the low-level text. For example, a code with both parts yields something like `"SSL - ... : X509 - ..."`.
5. **Truncation:** the output is always NUL-terminated. If the buffer is too small, the function returns with a shorter string rather than failing.

Two caveats from the index:

- `mbedtls_strerror` has a second body at `library/error.c:867`. The index lists both but I did not read the second one, and I can't tell from the index which build configuration selects which.
- `psa_strerror` in `programs/psa/` is a separate function for PSA status codes and is not on this path.

**What a contributor does to add a new code**

1. **Define the code** in the owning module's header as a negative macro, following `MBEDTLS_ERR_<MODULE>_<NAME>`. Examples: `MBEDTLS_ERR_CTR_DRBG_FILE_IO_ERROR` in `include/mbedtls/ctr_drbg.h` and `MBEDTLS_ERR_DHM_FILE_IO_ERROR` in `include/mbedtls/dhm.h`. Pick a value inside the module's existing range so it doesn't collide with another module's codes.
2. **Add a `case` to the right table.** A low-level code goes in `mbedtls_low_level_strerr`. A code that is its own module-level error goes in `mbedtls_high_level_strerr`. Use the `case -(MBEDTLS_ERR_...)` form and the existing `#if defined(MBEDTLS_<MODULE>_C)` guard, and keep the `"MODULE - description"` string format.
3. **Regenerate or edit the right file.** Both tables sit between `/* Begin Auto-Generated Code. */` markers. The index has no symbol for the generator, and a search for `generate_errors` returned nothing. Its file type may be one the index does not hold, since `.pl` files are not indexed. Check the repo's generator script before hand-editing that block, or the change will be overwritten on the next regeneration.
4. **Run the checks through pre-commit,** per your CLAUDE.md rules.

I did not verify which test covers the error-string tables. The index shows no covering tests for `mbedtls_strerror`.