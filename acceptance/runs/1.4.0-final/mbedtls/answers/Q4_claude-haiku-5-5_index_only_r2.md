**Short answer:** `mbedtls_strerror()` in `library/error.c` splits the code into a high-level and a low-level part, and looks up each part in a `switch` table. That table is generated from the public headers, so a contributor adds a new string by adding the `MBEDTLS_ERR_*` macro in a header and regenerating `error.c`, not by editing the table.

**The path, from a negative return to a string**

```
ret = -0x0F80 - ...           caller gets negative int
  │
  ▼
mbedtls_strerror(ret, buf, buflen)        library/error.c:792
  │  buflen==0 → return; memset buf to 0
  │  ret = -ret                           (make positive)
  │
  ├─ high = ret & 0xFF80                  (module bits)
  │    └─ mbedtls_high_level_strerr(ret)  error.c:174
  │         switch on high bits, e.g. "CIPHER - Authentication failed…"
  │         NULL → "UNKNOWN ERROR CODE (%04X)"
  │    SSL fatal alert (MBEDTLS_SSL_TLS_C)? → stop here, skip low level
  │
  ├─ low = ret & ~0xFF80                  (detail bits)
  │    (only if non-zero)
  │    if buf already has text: append " : "
  │    └─ mbedtls_low_level_strerr(ret)   error.c:537
  │         switch on low bits, e.g. "AES - Invalid key length"
  │         NULL → "UNKNOWN ERROR CODE (%04X)"
  │
  ▼
buf = "CIPHER - … : AES - …"   (truncated to buflen, always NUL-terminated)
```

Details that matter:

- The sign is dropped first, so the lookups compare positive values against `-(MBEDTLS_ERR_…)` cases.
- A code can carry both parts. The result is "high : low", and the separator is only written if there is room.
- Unknown codes are not silent. They come back as `UNKNOWN ERROR CODE (XXXX)` with the masked value, so the caller still sees a number.
- The two `switch` tables are wrapped in `#if defined(MBEDTLS_<MODULE>_C)` blocks, so a string only exists when its module is compiled in.

**How a contributor adds a new one**

I can't see the generator's internals from the index (see caveats), so the steps below come from what the code shows:

1. **Define the error macro** in the module's public header, with a negative value in that module's range. The high bits identify the module and the low bits the specific error. Use the existing `MBEDTLS_ERR_<MODULE>_*` macros as the pattern.
2. **Don't hand-edit `library/error.c`.** Its switch blocks sit between the `/* Begin Auto-Generated Code. */` markers. The build regenerates the file: `library/CMakeLists.txt:134` runs `scripts/generate_errors.pl` over `include/mbedtls` with `scripts/data_files/error.fmt`.
3. **Rebuild**, so the generator picks up the new macro and emits a `case` with its description string. The description follows the `MODULE - text` pattern.
4. **Check the gating.** The new case should land inside the same `#if defined(MBEDTLS_<MODULE>_C)` block as its siblings.
5. **Document it**, if it is user-visible. `docs/3.0-migration-guide.md` records past changes to error codes, which is the usual place for a removed or renamed one.

**Caveats**

- The generator script and `error.fmt` are not indexed, so I could not read how the generator selects headers or formats entries. Step 2 is confirmed by the CMake rule and the file header only.
- `library/error.c` appears in the index as a plain source file, while the CMake rule writes its output to the build directory. I could not tell whether the repo ships a checked-in copy that is regenerated, or whether the index read a build artefact. Check this before editing anything.
- The module-range convention and the exact header format are not verified here. Read an existing error header, such as the one for the module you're adding to, before writing the macro.