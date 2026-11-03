## Short answer

A negative return is never turned into text at runtime by a table you maintain by hand. The string lookup lives in `library/error.c`, which is generated from the `MBEDTLS_ERR_*` defines in `include/mbedtls/*.h` by `scripts/generate_errors.pl`. To add a new string, you add a documented `#define` to the right header and regenerate. Don't edit `error.c` directly.

## The runtime path

```
ret = -0x0020  (MBEDTLS_ERR_AES_INVALID_KEY_LENGTH)
   │
   ▼
mbedtls_strerror(ret, buf, buflen)          library/error.c:792
   │  buflen==0 → return; memset(buf,0)
   │  ret = -ret  (sign stripped)
   │
   ├─ high = ret & 0xFF80   (module part)
   │     └─ mbedtls_high_level_strerr(ret)   error.c:174
   │          switch on module code → "CIPHER - ..." / "DHM - ..." etc.
   │     (skipped for low-only codes; SSL fatal alert returns early)
   │
   ├─ low  = ret & ~0xFF80  (detail part)
   │     └─ mbedtls_low_level_strerr(ret)    error.c:537
   │          switch on detail code → "AES - Invalid key length" etc.
   │
   └─ joined as "HIGH : LOW" into buf;
      unknown code → "UNKNOWN ERROR CODE (XXXX)"
```

Key points from the code:

- **Two-level split.** Codes are split by the `0xFF80` mask. The high part identifies the module (`CIPHER`, `PK`, `X509`), the low part identifies the specific failure inside it. A caller can get both halves, which is why `mbedtls_strerror` concatenates them.
- **Two lookup tables, not one.** High-level modules (`CIPHER DHM ECP MD PEM PK PKCS12 PKCS5 RSA SSL X509 PKCS7`) and low-level modules (`AES ARIA ASN1 … SHA3 THREADING`) are listed separately in the generator. A new code goes into whichever switch matches its module.
- **Public API.** `mbedtls_strerror` is declared in `include/mbedtls/error.h:165`. The two helpers are declared at `error.h:180` and `error.h:195`.
- **Gating.** Each `case` block sits under `#if defined(MBEDTLS_<MODULE>_C)`, so a string only exists when its module is compiled in.

## What a contributor does to add a new code

1. **Add the define** in the module's header, e.g. `include/mbedtls/aes.h`, in the range the header already uses:
   ```c
   /** Invalid key length. */
   #define MBEDTLS_ERR_AES_INVALID_KEY_LENGTH   -0x0020
   ```
   The generator's regex requires `-0x…` with a leading minus.
2. **Write exactly one doxygen description**, either a `/** … */` block above the define or a `/**< … */` after it. Having both is a generator error, and having neither is also an error. A `\name` block is discarded, so don't use one for this.
3. **Use a unique value.** A duplicate value is a hard error (`Duplicated error code`).
4. **Make sure the module is known.** The module prefix must already be in `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`, otherwise the script exits with `Do not know how to handle`. A brand-new module must be added there, and its `MBEDTLS_<MODULE>_C` config symbol must exist for the gating to work.
5. **Make sure the header is included by the generator's scan.** The script only emits `#include "mbedtls/<module>.h"` for headers it matched, and it errors if a header has codes but is not included by the library.
6. **Regenerate.** Run through the build, which invokes `library/Makefile:355-360` or the CMake rule in `library/CMakeLists.txt:136-144`. Running the script directly is equivalent but the build owns the flags, so route through the build for the same reason the repo's CLAUDE rules give for pre-commit.
7. **Commit the regenerated `library/error.c` too.** It is tracked in git (`git ls-files` lists it). The `.gitignore` entry for it is commented out, so it is not ignored.

Two things I did not verify: I did not check whether a test in the test suite specifically exercises every new string, and I did not run the generator here. The regeneration steps above are from reading `generate_errors.pl` and the Makefile, not from running them.