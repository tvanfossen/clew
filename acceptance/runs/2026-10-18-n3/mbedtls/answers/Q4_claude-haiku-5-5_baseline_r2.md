**Short version:** `mbedtls_strerror()` in `library/error.c` negates the code, splits it into a high-level part and a low-level part, and looks each part up in a `switch`. That `switch` is generated, so adding a message means adding a `#define` with a Doxygen comment and regenerating, not hand-editing `error.c`.

## How a negative code becomes a string

```
ret (e.g. -0x7780)
  │
  ▼
mbedtls_strerror(ret, buf, buflen)        library/error.c:792
  ├─ buflen == 0 → return; else zero buf
  ├─ ret = -ret                            (sign dropped)
  ├─ ret & 0xFF80 ?  (high-level bits)
  │     └─ mbedtls_high_level_strerr(ret) → "SSL - ..."  (or "UNKNOWN ERROR CODE (xxxx)")
  │        └─ if high == SSL FATAL_ALERT → return early (don't decode the alert's low bits)
  ├─ ret & ~0xFF80 ?  (low-level bits)
  │     ├─ if high text already present → append " : "
  │     └─ mbedtls_low_level_strerr(ret) → "ERROR - ..."  (or "UNKNOWN ERROR CODE (xxxx)")
  ▼
buf: e.g. "SSL - A fatal alert message was received from our peer"
```

- The 16-bit layout (`include/mbedtls/error.h:17`) is 3 bits of high-level module ID plus 7 bits of low-level code. The split mask is `0xFF80`.
- Each lookup is a `switch` over `case -(MBEDTLS_ERR_...)` labels, grouped by module. Those labels and the description strings are emitted by the generator.
- If no description matches, the caller gets `UNKNOWN ERROR CODE (XXXX)` rather than nothing.
- When `MBEDTLS_ERROR_C` is disabled, a dummy `mbedtls_strerror` at `error.c:867` just writes an empty string.

## Where the table comes from

`library/error.c` is a build artifact. `scripts/generate_errors.pl` produces it from `scripts/data_files/error.fmt` (the template) plus the headers in `include/mbedtls/*.h`.

The generator:
1. Scans every header for this pattern: `/** ...doc... */` before or `/**< ...doc... */` after, then `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....`. Exactly one of the two doc comments must be present, or it dies.
2. Dies on duplicate numeric codes.
3. Maps the `<MODULE>` prefix to an `#if defined(MBEDTLS_<MODULE>_C)` guard and a `low_level` or `high_level` switch. A module missing from its hard-coded `@low_level_modules` / `@high_level_modules` lists causes an exit with `Do not know how to handle`.
4. Derives the include name from the module (lowercased, `NET` → `net_sockets`) and checks that header is among the included files, or errors.

Regeneration is wired into `library/Makefile:355`, `library/CMakeLists.txt:134`, and `tests/scripts/check-generated-files.sh`. CI flags a stale `error.c`.

## What a contributor has to do

1. **Define the code** in the header for its module, such as `include/mbedtls/<module>.h`. Use the form `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x<hex>` with a Doxygen doc comment, placed before or after, not both. Pick a value that is free in the module's range (the table at `error.h:37-80` lists the assignments).
2. **If the module is new**, add it to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl:31-38`. Also add the guard and header mapping if the prefix doesn't follow the default rule.
3. **Regenerate**: `perl scripts/generate_errors.pl` from the repo root, or run `make` in `library/`, or let CMake's custom command do it. Don't edit `library/error.c` by hand.
4. **Verify**: `tests/scripts/check-generated-files.sh` should be clean, and the `test_suite_error` tests (`tests/suites/test_suite_error.data`) should cover the new string. Add a case there if the code is user-visible.
5. Add a ChangeLog entry if the change is user-visible. The repo keeps one.

Caveat I did not run: I read the generator and `error.c` but did not run the script or the test suite, so the exact failure messages are from reading the code.