**How a negative code becomes a string**

Everything goes through `mbedtls_strerror(int ret, char *buf, size_t buflen)` in `library/error.c:792`. It returns `void`, and its declaration is in `include/mbedtls/error.h:165`.

```
ret (e.g. -0x7A00)
  │ buflen==0 → return; memset(buf,0)
  │ ret<0 → ret = -ret
  ▼
high = ret & 0xFF80 ──► mbedtls_high_level_strerr()  (error.c:174)
  │   "CIPHER - Bad input parameters"  or  "UNKNOWN ERROR CODE (xxxx)"
  │   if high == -MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE → return (no low part)
  ▼
low = ret & ~0xFF80 → if 0, done
  │   if high text was written: append " : " (needs ≥5 bytes, else return)
  ▼
mbedtls_low_level_strerr() (error.c:537)
      "ASN1 - Data is invalid"  or  "UNKNOWN ERROR CODE (xxxx)"
```

- **Two halves.** The top bits (mask `0xFF80`) identify the module; the low 7 bits identify the specific error within it. Each half is looked up separately in a `switch`.
- **Output shape.** A two-part code reads as `MODULE - high text : MODULE - low text`. A code with only a high part gives just that text.
- **Truncation.** The buffer is always NUL-terminated and silently truncated to `buflen`.
- **Config gating.** The whole function and both tables sit under `MBEDTLS_ERROR_C`. The index also shows a second `mbedtls_strerror` at `error.c:867` under `MBEDTLS_ERROR_STRERROR_DUMMY`, which I take to be the no-strings fallback, but I did not read that body.
- **Generated tables.** Each lookup's body is wrapped in a `// Begin Auto-Generated Code` block, with one `#if defined(MBEDTLS_<MODULE>_C)` section per module. The generator is `scripts/generate_errors.pl`, whose header says it writes `error.c` from an include directory and a data directory.

**Adding a new error string**

1. Add the `MBEDTLS_ERR_<MODULE>_<NAME>` define in the module's header, with a negative value in that module's range. The index does not confirm which range is free, so check the existing defines first.
2. Do not hand-edit the auto-generated cases in `library/error.c`. Regenerate them with `scripts/generate_errors.pl`, run through the repo's `pre-commit` or task entry point, not the script directly.
3. Check the generated case appears under the right `MBEDTLS_<MODULE>_C` guard and that the description text is what you wrote.
4. Commit the header and regenerated `error.c` together. The repo's `ChangeLog.d` directory suggests a changelog entry is expected, but I have not confirmed that convention in the index.

**What I could not verify:** the generator's body and its template file (`.fmt` and `.data` files are not in the index), so I cannot say where the description text comes from or the exact regeneration command. Reading `scripts/generate_errors.pl` and its data template will settle both.