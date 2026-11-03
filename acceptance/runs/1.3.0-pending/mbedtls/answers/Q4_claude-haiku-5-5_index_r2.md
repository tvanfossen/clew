**Short answer:** the caller passes the negative code to `mbedtls_strerror()`, which splits it into a high-level part and a low-level part and looks each up in a `switch` table in `library/error.c`. That table is generated from the `MBEDTLS_ERR_*` defines in `include/mbedtls/*.h`, so a contributor adds a code by adding a documented define and regenerating, not by hand-editing `error.c`.

**Runtime path**

```
mbedtls_strerror(ret, buf, buflen)              library/error.c:792
  ├─ buflen == 0 → return; else memset(buf, 0)
  ├─ ret = -ret                                  (sign dropped)
  ├─ high = ret & 0xFF80
  │    └─ mbedtls_high_level_strerr(ret)         error.c:174  switch → "CIPHER - Bad input parameters"
  │       fallback: "UNKNOWN ERROR CODE (%04X)"
  │       if high code is SSL fatal alert → return (skip low level)
  ├─ low = ret & ~0xFF80
  │    └─ if low != 0: append " : " if buffer has room
  │       mbedtls_low_level_strerr(ret)         error.c:537  switch → "AES - Invalid key length"
  │       fallback: "UNKNOWN ERROR CODE (%04X)"
  └─ result: "HIGH : LOW", or whichever part exists, truncated to buflen
```

- **Sign:** the caller's `-0x0020` becomes `0x0020` before any table lookup. Each `case` label is written `-(MBEDTLS_ERR_…)`, so it compares against the positive value.
- **Two tables:** the bits in `0xFF80` select a module, such as CIPHER, DHM, ECP or SSL. The low 7 bits select a leaf error within the low-level module, such as AES, ASN1 or BASE64. A single code can carry both parts.
- **Truncation:** the buffer is always null-terminated. If fewer than 5 bytes remain before the `" : "` separator, the low-level part is dropped.
- **Disabled builds:** with `MBEDTLS_ERROR_C` off, the `#else` branch at `error.c:867` is a dummy that writes an empty string. `MBEDTLS_ERROR_STRERROR_DUMMY` keeps the symbol without the tables.

**Generation**

`scripts/generate_errors.pl` builds `library/error.c` from `scripts/data_files/error.fmt`. It:

1. Scans every `include/mbedtls/*.h` for `#define MBEDTLS_ERR_X -0x…` with a Doxygen comment before or after it. Both, or neither, is a hard error.
2. Takes the module from the second name token, with fixes: `MPI→BIGNUM`, `CTR→CTR_DRBG`, `HMAC→HMAC_DRBG`, `NET→net_sockets`.
3. Dies on an unknown module, on a duplicate error value, and on a header that defines codes but is not included.
4. Groups cases under `#if defined(MBEDTLS_<MODULE>_C)` and emits the description as `"MODULE - description"`, with the trailing period stripped.

The Makefile (`library/Makefile:355`) and CMake (`library/CMakeLists.txt:136-144`) regenerate `error.c` when headers change. `tests/scripts/check-generated-files.sh:135` fails CI if the committed file is stale.

**To add a new code**

1. Pick the module prefix. It determines the string shown (`MBEDTLS_ERR_MPI_*` displays as `BIGNUM`).
2. Add the define to the module's header with a doxygen comment, either before or after but not both, and a value not already in use:
   ```c
   /** Something specific went wrong. */
   #define MBEDTLS_ERR_FOO_SOMETHING_WRONG   -0x0031
   ```
   Use a low-level value (below `0x80`) for leaf errors. Use a high-level value (a multiple of `0x80`) only if the module needs its own top-level slot.
3. If the prefix is a new module, add it to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`. Otherwise it dies with "Do not know how to handle". Map its `#if` gate too if the config symbol isn't `MBEDTLS_<MODULE>_C`.
4. Regenerate with `make` in `library/` or the CMake build, or run `perl scripts/generate_errors.pl` from the repo root. Don't hand-edit `library/error.c`.
5. Commit the header and the regenerated `error.c` together, and run the repo's pre-commit or test gate.
6. Verify with `programs/util/strerror.c` (`strerror -0x0031`) or a test that asserts the exact string.

**Not verified:** I read the code but did not run the generator or the build, so the steps above come from the scripts, not from a run.