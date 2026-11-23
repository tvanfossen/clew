**Short version:** `mbedtls_strerror()` splits the integer into a module part and a low-level part, looks each up in a generated `switch`, and joins the results. To add a string you add the error macro in its module header and regenerate the table, not hand-edit it. I could not confirm the generator's exact inputs from the index.

**Runtime path (`library/error.c`)**

```
mbedtls_strerror(ret, buf, buflen)                       error.c:792
 ├─ buflen == 0 → return; memset buf to 0
 ├─ ret < 0 → ret = -ret
 ├─ high = ret & 0xFF80  → mbedtls_high_level_strerr(ret)   error.c:174
 │     switch over module codes, one #if block per module (CIPHER, DHM, ECP, …)
 │     no match → "UNKNOWN ERROR CODE (%04X)"
 │     SSL fatal-alert code → return here, skip the low-level part
 ├─ low = ret & ~0xFF80  → if 0, return (high-level text only)
 ├─ if high text already present → append " : "
 └─ mbedtls_low_level_strerr(ret)                          error.c:537
       switch over low-level codes (AES, ASN1, BASE64, BIGNUM, …)
       no match → "UNKNOWN ERROR CODE (%04X)"
```

- The caller passes a negative value (for example `MBEDTLS_ERR_AES_BAD_INPUT_DATA`). The function takes the magnitude, so the table cases are written as `-(MBEDTLS_ERR_…)`.
- Output is written with `mbedtls_snprintf`, so it is truncated to `buflen` and always null-terminated. The index's doc for `mbedtls_strerror` says this.
- Both lookup functions are generated code. The index shows each module's cases wrapped in `#if defined(MBEDTLS_<MODULE>_C)`, so a string exists only in builds where that module is enabled.
- The whole path is gated by `MBEDTLS_ERROR_C`. `MBEDTLS_ERROR_STRERROR_DUMMY` is a config symbol that gates the same code.

**Adding a new string**

1. Define the new `MBEDTLS_ERR_<MODULE>_<NAME>` macro in the module's public header under `include/mbedtls/`, as a negative value in the existing pattern.
2. Do not edit the `Begin Auto-Generated Code` block in `library/error.c` by hand. Regenerate it with `scripts/generate_errors.pl`, whose usage is `include_dir data_dir error_file`. The script's header comment says it generates `error.c`.
3. Check that the generated `case` lands inside the right `#if defined(MBEDTLS_<MODULE>_C)` block.
4. Run the gate through pre-commit as the repo requires.

**What I could not verify**

- The index does not read `scripts/generate_errors.pl` (it has zero symbols) or the `.data` files (140 are excluded from the index). So I cannot confirm what the generator scans for the code list and the description text, or whether the descriptions come from test data files. Read the script before relying on step 2.
- The index does not show a test that exercises every string. Check `tests/` directly for that.