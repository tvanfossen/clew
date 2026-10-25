The index answers the lookup half fully. It does not show the generator for the string tables, so the contributor half is only partly confirmed.

**How a negative code becomes a string**

```
ret (e.g. -0x7300)
  │
  ▼
mbedtls_strerror(ret, buf, buflen)        library/error.c:792
  │  buflen==0 → return; memset(buf, 0)
  │  ret = -ret                           (work on the positive value)
  │
  ├─ high = ret & 0xFF80                  module part
  │    └─ mbedtls_high_level_strerr(ret)  error.c:174  (switch over module codes)
  │         NULL → "UNKNOWN ERROR CODE (%04X)"
  │    └─ if high is SSL fatal alert → return now (skip low part)
  │
  ├─ low = ret & ~0xFF80                  specific error part
  │    └─ if buf already has text, append " : " (needs ≥5 bytes left)
  │    └─ mbedtls_low_level_strerr(ret)   error.c:537  (switch over specific codes)
  │         NULL → "UNKNOWN ERROR CODE (%04X)"
  ▼
buf = "MODULE - description [ : MODULE - description ]", truncated, NUL-terminated
```

1. **Caller side.** Mbed TLS functions return a code built at the failure site with `MBEDTLS_ERROR_ADD(high, low)`. That macro calls `mbedtls_error_add`, which returns `high + low`. File and line are only recorded under `MBEDTLS_TEST_HOOKS`. So a returned value is a module-level code plus an optional specific code, OR-ed into one integer.
2. **Entry point.** `mbedtls_strerror` is declared in `include/mbedtls/error.h:165` and defined in `library/error.c:792`. It only exists when `MBEDTLS_ERROR_C` is enabled. The index also shows a `MBEDTLS_ERROR_STRERROR_DUMMY` gate, and a second `mbedtls_strerror` definition at `error.c:867`. I believe that is the dummy stub, but the index does not label it, so I'm not certain.
3. **Splitting.** The sign is dropped, then the value is split on the `0xFF80` mask. The high part goes to `mbedtls_high_level_strerr`, and the low part (`~0xFF80`) goes to `mbedtls_low_level_strerr`. The two parts are joined with `" : "`.
4. **Lookup.** Both functions are large `switch` statements in `library/error.c`, under a comment marked "Begin Auto-Generated Code". Each case is wrapped in `#if defined(MBEDTLS_<MODULE>_C)` and returns a string like `"<MODULE> - description"`. An unknown code yields `UNKNOWN ERROR CODE (XXXX)`.
5. **Early exit.** If the high part is an SSL fatal alert, the low part is not translated.

**Adding a new one**

The index confirms the pattern but not every step:

1. **Define the macro** as a negative hex value in the module's public header, following neighbours such as `MBEDTLS_ERR_SSL_INTERNAL_ERROR` = `-0x6C00` in `include/mbedtls/ssl.h:125`. It must fall in that module's range so the high-level mask works.
2. **Add a `case` to the matching table** in `library/error.c`: `mbedtls_high_level_strerr` for a module-level code, or `mbedtls_low_level_strerr` for a specific one. Put it inside the module's `#if defined(MBEDTLS_<MODULE>_C)` block with a `"MODULE - text"` string. The index shows no generator script for these tables: a search for `generate_errors` returned nothing, and `.pl` files are not indexed. The "Auto-Generated" marker suggests the tables may be produced by a script, so check for one before hand-editing. I could not confirm which, if any, exists.
3. **Raise it at the failure site** with `MBEDTLS_ERROR_ADD(high, low)`.
4. **Compatibility.** `BRANCHES.md` says a new error condition for an existing function is a backwards-compatibility matter. The index does not show the full policy, so read that file before changing what an existing function returns.
5. **Changelog.** `ChangeLog.d/` exists in the repo. The index does not show the required entry format.

**Gaps.** The index shows no covering tests for `mbedtls_strerror`, so I can't say which test exercises the string path. I also couldn't read the full contents of the two switch tables, which the index truncated.