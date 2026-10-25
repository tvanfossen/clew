**Short answer:** the caller passes the negative code and a buffer to `mbedtls_strerror()`. That function splits the code into a high-level part and a low-level part, looks each up in a switch table in `library/error.c`, and joins the two strings. Adding a new code means defining a macro in the module header and adding a matching case to the table. The table is marked as auto-generated, so the table edit should come from the generator, not by hand.

**The path, step by step**

```
mbedtls_xxx() returns e.g. -0x2A80
        │
        ▼
mbedtls_strerror(ret, buf, buflen)            library/error.c:792
  1. buflen==0 → return; memset buf to 0
  2. ret = -ret                              (work with positive value)
  3. high = ret & 0xFF80 → mbedtls_high_level_strerr()   error.c:174
       NULL → "UNKNOWN ERROR CODE (xxxx)"
       SSL fatal alert → return early, skip low level
  4. low = ret & ~0xFF80 → if 0, done
  5. if buf already has high text, append " : "
  6. mbedtls_low_level_strerr()               error.c:537
       NULL → "UNKNOWN ERROR CODE (xxxx)"
  7. write result into buf (always NUL-terminated, truncated if needed)
```

- **Bit layout:** `include/mbedtls/error.h` documents a 16-bit layout. The top 3 bits after the sign identify the high-level module (PEM, X509, SSL, and so on). The next 5 bits are a module-specific code. The low 7 bits (`0x007F`) are the low-level module code (AES, MPI, NET, and so on). The header also lists the code ranges assigned to each module.
- **Two lookup tables:** both are switch statements under the banner `/* Begin Auto-Generated Code. */`. Each case is wrapped in the module's `#if defined(MBEDTLS_xxx_C)`, so only compiled-in modules appear. For example, `MBEDTLS_ERR_AES_BAD_INPUT_DATA` is `-0x0021` in `include/mbedtls/aes.h:50`, and `mbedtls_low_level_strerr` returns `"AES - Invalid input data"` for it.
- **Caller-facing API:** `include/mbedtls/error.h:165` declares `mbedtls_strerror(int, char *, size_t)`. The definition is in `library/error.c`, and the whole file is gated by `MBEDTLS_ERROR_C`. The `MBEDTLS_ERROR_STRERROR_DUMMY` config symbol also gates it, and `configs/config-symmetric-only.h` turns that symbol on. I did not confirm what the second overload at `error.c:867` does, though it is probably the dummy variant.
- **Example consumers:** `programs/test/benchmark.c` (`PRINT_ERROR`) and `programs/util/strerror.c` (a CLI that decodes an integer, hex included).

**Adding a new error code**

1. **Define the macro** in the owning module's public header, for example `include/mbedtls/<module>.h`, as `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x00XX`. Choose a value that fits that module's range in the `error.h` table. Check for collisions there too. A high-level code goes in the high-level table, and a low-level code in the low-level table.
2. **Add a case to the table** in `library/error.c`. Each lookup has a case of the form `case -(MBEDTLS_ERR_<MODULE>_<NAME>): return("<MODULE> - <message>");`, placed in the module's `#if` block. The string should follow the existing `MODULE - sentence` style.
3. **Regenerate rather than hand-edit.** The switch bodies sit in the "Auto-Generated Code" section. The generator script is in `scripts/` as a `.pl` file, which this index does not cover, so I can't name it or confirm the exact command. Check the repo's build docs or the `.pl` in `scripts/` before editing, or the change will be overwritten on the next regeneration.
4. **Add a test and a ChangeLog entry.** The repo has a top-level `ChangeLog.d/` directory. I did not verify the test convention from the index, so check the existing error-string tests before writing one.

**What the index could not settle:** the generator script and its invocation, and any test that covers `mbedtls_strerror`. The index lists no covering tests for it, and its `.pl` and build-script inputs are not indexed.