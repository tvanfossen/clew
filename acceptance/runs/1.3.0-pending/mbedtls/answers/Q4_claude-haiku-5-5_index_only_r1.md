**Short answer:** the string comes from `mbedtls_strerror()` in `library/error.c`, which splits the code into a high-level and a low-level half and looks up each half in a generated `switch`. To add one, you add a `MBEDTLS_ERR_*` macro to the module's public header and let the CMake-driven generator rebuild `error.c`. I could not confirm where the description text itself is written, so check that before adding one.

**The lookup path**

```
ret (negative, e.g. -0x0021)
  │
  ▼
mbedtls_strerror(ret, buf, buflen)          library/error.c:792
  ├─ buflen == 0 → return; else memset(buf, 0)
  ├─ ret = -ret                              (work with positive value)
  ├─ high = ret & 0xFF80
  │    └─ mbedtls_high_level_strerr(ret)    error.c:174 (switch)
  │         → "CIPHER - Bad input parameters", or "UNKNOWN ERROR CODE (XXXX)"
  │    └─ if high == SSL fatal alert → return early
  ├─ low = ret & ~0xFF80  (the low 7 bits)
  │    └─ if low != 0: append " : " (only if buf already has text, and only if ≥5 bytes remain)
  └─ mbedtls_low_level_strerr(ret)          error.c:537 (switch)
       → "AES - Invalid input data", or "UNKNOWN ERROR CODE (XXXX)"
```

- Each `case` is `-(MBEDTLS_ERR_X)` and sits under `#if defined(MBEDTLS_X_C)`. If a module is compiled out, its strings are compiled out and its codes come back as `UNKNOWN ERROR CODE`.
- The 0xFF80 mask means module groups are on 0x80 boundaries, and the low 7 bits identify the specific error. `mbedtls_error_add()` in `include/mbedtls/error.h:142` is the high+low combiner.
- The index lists a second `mbedtls_strerror` at `error.c:867`. I think it is the stub variant gated by `MBEDTLS_ERROR_STRERROR_DUMMY`, but that is an inference from the gate lists.

**Where the table comes from**

- `library/CMakeLists.txt:134` runs `scripts/generate_errors.pl` over `include/mbedtls` and `scripts/data_files`, writing `error.c` into the build directory. Its dependencies are the script, the error headers, and `scripts/data_files/error.fmt`.
- The index marks `error.c` as generated, so `library/error.c` in the repo may be a stale or checked-in copy. I can't tell from the index which one it read. Don't hand-edit the "Begin Auto-Generated Code" region.

**To add a new code**

1. Add `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x00XX` in the module's public header, e.g. `include/mbedtls/aes.h:50` for `AES_BAD_INPUT_DATA` (`-0x0021`). Keep the value in that module's band and in the low 7 bits if it is a specific error.
2. Provide the description text. **I could not verify where it goes.** `generate_errors.pl` has no indexed symbols and `error.fmt` is not indexed, so the index cannot show how the generator reads the text. Read the script and `scripts/data_files/error.fmt` before writing it.
3. Rebuild through the normal CMake target so the generator regenerates `error.c`.
4. Test the string appears with the module enabled. Also test that a disabled module falls back to `UNKNOWN ERROR CODE`, since that is how the `#if` guard behaves.