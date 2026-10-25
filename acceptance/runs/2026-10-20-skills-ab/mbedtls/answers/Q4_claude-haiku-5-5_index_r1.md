**Short answer:** the caller passes the negative code to `mbedtls_strerror()`. It negates the value, splits it into a high-level part and a low-level part, and looks each part up in a switch table that is generated from the `MBEDTLS_ERR_*` defines in the headers. A contributor adds a string by adding a `#define` with a doc comment to the right header, then regenerating `library/error.c`. Don't edit `error.c` by hand.

**The lookup path**

```
caller: mbedtls_strerror(-0x7280, buf, len)
          │
          ├─ ret = -ret                          (error.c:792, mbedtls_strerror)
          ├─ high = ret & 0xFF80 ──► mbedtls_high_level_strerr(ret)   (error.c:174)
          │                           switch over MODULE_CODE; "CIPHER - Bad input…"
          │                           NULL ─► "UNKNOWN ERROR CODE (%04X)"
          ├─ if high is MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE: return early
          ├─ low = ret & ~0xFF80 ──► mbedtls_low_level_strerr(ret)    (error.c:537)
          │                           switch over low-level codes; "AES - Invalid key length"
          └─ join as "HIGH : LOW" in buf, truncated to buflen, always NUL-terminated
```

- The mask `0xFF80` picks the module bits, and the low 7 bits hold the low-level code. This matches the layout comment in `include/mbedtls/error.h:17-37`.
- A code can have both parts. For example, an SSL error can come back as `"SSL - … : <low-level text>"`. The one exception is a fatal-alert SSL error, which returns after the high-level part and skips the low-level lookup.
- If `MBEDTLS_ERROR_C` is off, the dummy `mbedtls_strerror` at `error.c:144` just writes an empty string.

**The generated part**

`library/error.c` is generated, and the switch bodies between the "Begin/End Auto-Generated Code" markers come from `scripts/generate_errors.pl` using `scripts/data_files/error.fmt`. The script:

1. Reads every `include/mbedtls/*.h`, matching `#define MBEDTLS_ERR_<X> -0x....` with its doc comment.
2. Splits the codes by module name into the low-level list or the high-level list (lines 36-43).
3. Emits one `case -(MBEDTLS_ERR_X):` per code, wrapped in `#if defined(MBEDTLS_<MODULE>_C)`.

The build regenerates the file automatically: CMake in `library/CMakeLists.txt:133-150` and make in `library/Makefile:355-360`. A CI check, `tests/scripts/check-generated-files.sh:135`, compares the committed `error.c` with the generator's output.

**What a contributor does to add a new code**

1. Add the define in the module's header under `include/mbedtls/`, with a doc comment placed either before it (`/** … */`) or after it (`/*!< … */`), not both. The script aborts if a code has no description or has two.
2. Pick a value that is not already used. The script aborts with "Duplicated error code" otherwise.
3. If the module is new, add its name to `@low_level_modules` or `@high_level_modules` in `generate_errors.pl:36-43`. Otherwise it aborts with "Do not know how to handle".
4. Regenerate: run `make error.c` in `library/`, or run `perl scripts/generate_errors.pl` from the repo root. A normal build does this too.
5. Commit the header change and the regenerated `library/error.c` together, or the generated-files check will fail.

**Things that are easy to miss**

- A description is the text after `MODULE -`, so keep it to one line. Backslashes are escaped by the script.
- The string only exists when the module's `MBEDTLS_*_C` option is enabled, because of the `#if` wrapper.
- The index does not contain the Perl script or `error.fmt`, so I read those files directly. The index does cover `error.c`, `error.h`, and the two lookup functions, which is where the answer above came from.