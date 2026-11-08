**How a negative code becomes a string**

The entry point is `mbedtls_strerror(int ret, char *buf, size_t buflen)` in `library/error.c:792`. It is declared in `include/mbedtls/error.h`, and the index shows a second definition at `error.c:867`, which I think is the `MBEDTLS_ERROR_STRERROR_DUMMY` branch, though I haven't confirmed that.

```
mbedtls_strerror(ret, buf, buflen)                 library/error.c:792
 ├─ buflen==0 → return; memset(buf,0)
 ├─ ret = -ret                                      (make positive)
 ├─ high = ret & 0xFF80 ─→ mbedtls_high_level_strerr()   error.c:174
 │     switch on module code → "CIPHER - Authentication failed …"
 │     unknown → "UNKNOWN ERROR CODE (%04X)"
 │     SSL fatal-alert high code → return early, skip low part
 ├─ low = ret & ~0xFF80 → if 0, return
 ├─ if high was written, append " : " and continue after it
 └─ low → mbedtls_low_level_strerr()               error.c:537
       switch on low bits → "AES - Invalid key length"
       unknown → "UNKNOWN ERROR CODE (%04X)"
```

So the output is either a high-level description, a low-level one, or `high : low`. The buffer is always NUL-terminated and truncated with `snprintf` if it is too small.

Both lookup functions are large `switch` statements between `/* Begin Auto-Generated Code */` markers. Each case is wrapped in the owning module's `#if defined(MBEDTLS_xxx_C)`, so a code has a string only when its module is compiled in. The index also gates `error.c` itself on `MBEDTLS_ERROR_C`.

**Where the switch cases come from**

`library/CMakeLists.txt:134` runs `scripts/generate_errors.pl` to produce `error.c` from the error headers under `include/mbedtls` plus `scripts/data_files/error.fmt`. The output is written to the build directory, so `error.c` is generated and should not be hand-edited.

I could not read the generator or its data files. `scripts/generate_errors.pl` shows no harvested symbols, and `.fmt` files are not in the index. The steps below are inferred from the CMake wiring and the generated output, not checked against the script.

**Adding a new code (inferred)**

1. **Define the macro** in the module's public header, e.g. `#define MBEDTLS_ERR_FOO_BAR -0x....`. Use the module's existing band; the top bits identify the module, for example `SSL_INTERNAL` is `-0x6C00` and `X509_FATAL` is `-0x3000`.
2. **Respect the split.** Low-level codes live in bits 0–6 (`& ~0xFF80`), so a module's own code must be in `0x01`–`0x7F`. A new module needs a high-level band in bits 7–15.
3. **Add its description** to `scripts/data_files/error.fmt`, the format file the generator reads. The exact entry format is unverified.
4. **Rebuild.** The headers are dependencies of the custom command, so the generator reruns and adds a `case` under the module's `#if`.
5. **Test.** The index lists no covering tests for `mbedtls_strerror`. Check that the new string appears through `programs/util/strerror.c`, which prints the description for an integer status.