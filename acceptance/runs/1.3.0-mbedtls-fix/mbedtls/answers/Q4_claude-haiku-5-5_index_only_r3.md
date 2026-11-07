**How a negative code becomes a string**

1. A caller passes the negative `int` and a buffer to `mbedtls_strerror(ret, buf, buflen)` (`library/error.c:792`). It is `void`, so it reports nothing back. It zeroes the buffer, returns early if `buflen` is 0, and negates `ret` if it is negative.
2. It splits the magnitude into two parts:
   - **High-level** = `ret & 0xFF80`, the module part (CIPHER, PEM, SSL, and so on).
   - **Low-level** = `ret & ~0xFF80`, the specific error within that module.
3. The high-level part goes to `mbedtls_high_level_strerr()` (`error.c:174`), a `switch` with one `case` per code. Each case is wrapped in its module's `#if` (for example `MBEDTLS_CIPHER_C`), so a module compiled out has no entry. An unmatched code writes `UNKNOWN ERROR CODE (%04X)`.
4. If the error is `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`, it returns early and does not decode the low part (`MBEDTLS_SSL_TLS_C` only).
5. If there is a low-level part, it is appended with `" : "`. It comes from `mbedtls_low_level_strerr()` (`error.c:537`), another `switch` in the same style, covering AES, ASN1, MPI, NET and so on. Unmatched codes get the same `UNKNOWN` fallback.
6. The buffer always ends with a NUL, and the output is truncated if it does not fit.

```
ret (negative) → negate → split
   ├─ high = ret & 0xFF80  → high_level_strerr() → "PEM - ..."
   └─ low  = ret & ~0xFF80 → low_level_strerr()  → " : ..."  (skipped for SSL fatal alert)
```

The codes are composed by `MBEDTLS_ERROR_ADD(high, low)` (`include/mbedtls/error.h:113`), which calls `mbedtls_error_add()`. That function returns `high + low` and, under `MBEDTLS_TEST_HOOKS`, also calls a test hook.

**Adding a new string**

`library/error.c` is generated, not hand-maintained. Both switch bodies are marked "Begin Auto-Generated Code", and `scripts/generate_errors.pl` is documented as "Generate error.c", taking an include dir, a data dir and an output file. So the change is:

1. Define the new `MBEDTLS_ERR_<MODULE>_<NAME>` in the module's public header, and combine it with `MBEDTLS_ERROR_ADD` in the code that returns it.
2. Add its name and description to the generator's data input in the data directory, then regenerate `library/error.c` through the generator. Do not edit the `case` lines by hand, or the next regeneration will overwrite them.
3. Keep the module `#if` guard the generator emits, so the string disappears with the module.

**What I could not verify from the index**

- The `.fmt` data-file format and the exact regeneration command. The index does not hold `.fmt` files (`not_indexed: .fmt=3`), and the generator script has no indexed symbols, so I could not read how it takes a name and description.
- The exact `#define` form that a module header uses for each code. I confirmed only that the bodies compare against negated `MBEDTLS_ERR_*` macros.
- `error.c` has a second `mbedtls_strerror` definition at line 867, gated by `MBEDTLS_ERROR_STRERROR_DUMMY`. I did not read it, so I can't say which build uses it.

Confirming the second and third items needs the `.fmt` files and `scripts/generate_errors.pl` read directly.