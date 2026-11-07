**Short version:** the string comes from a generated `switch` in `library/error.c`. That file is produced by `scripts/generate_errors.pl` from `MBEDTLS_ERR_*` macros in `include/mbedtls/*.h`, so a new string means adding a documented macro and regenerating, not hand-editing the switch.

**Runtime path**

```
caller: mbedtls_strerror(ret, buf, sizeof buf)            library/error.c:792
  ├─ buflen==0 → return; memset(buf, 0)
  ├─ ret = -ret                                  (sign dropped; codes are stored negative)
  ├─ ret & 0xFF80  → mbedtls_high_level_strerr(ret)    error.c:174  (module-level switch)
  │     └─ if SSL fatal-alert wrapper → return, skip low level
  ├─ ret & ~0xFF80 → mbedtls_low_level_strerr(ret)     error.c:537  (specific-code switch)
  └─ joins as "HIGH : LOW"; unknown → "UNKNOWN ERROR CODE (%04X)"
```

- The high-level part (mask `0xFF80`) names the module, for example `CIPHER - ...`, `X509 - ...`. The low-level part names the specific failure, for example `AES - Invalid key length`, and each is looked up in its own switch.
- Both switches are fully generated between `Begin Auto-Generated Code` and `End Auto-Generated Code`. Each case is `case -(MBEDTLS_ERR_X): return "MODULE - description";`, wrapped in `#if defined(MBEDTLS_<MOD>_C)`.
- If `MBEDTLS_ERROR_C` is off, `mbedtls_strerror` is a dummy that writes an empty string. `MBEDTLS_ERROR_STRERROR_DUMMY` keeps the tables compiled in some configs. Both gates are in `configs/` and `include/mbedtls/mbedtls_config.h`.

**What a contributor does to add one**

1. **Define the macro** in the module's public header, for example `include/mbedtls/cipher.h`. Use the `-0x` form, because the generator's regex only matches `-0x…`:
   ```c
   /** Description of the failure. */
   #define MBEDTLS_ERR_CIPHER_FOO  -0x6310
   ```
   Give it exactly one description, either a `/** */` comment before it or a `/**< */` comment after it. The generator dies on both or neither. Don't reuse a value: duplicates are fatal.
2. **If the module prefix is new**, add it to `@low_level_modules` or `@high_level_modules` in `scripts/generate_errors.pl`. An unknown module makes the script exit with an error. Also make sure the header's `MBEDTLS_<MOD>_C` gate exists. The generator derives the `#if` and `#include "mbedtls/<module>.h"` lines from the module name.
3. **Regenerate `library/error.c`** through the build. The rule is at `library/Makefile:355-360` and the CMake rule is in `library/CMakeLists.txt:136-144`. Don't edit the generated block by hand.
4. **Verify.** `tests/scripts/check-generated-files.sh` reruns the generator and fails if the committed `error.c` differs. `tests/suites/test_suite_error.data` is the existing test suite for the error API, and I didn't read it in detail. Add a case there, and check it fails before the change. Run the gate through pre-commit as the repo expects.

**Caveats I did not verify**

- I did not run the generator or the test suite.
- The generator checks the module list, not the value. A new code must sit in the bit range its class uses, the `0xFF80` high-level bits versus the low bits, or `mbedtls_strerror` will never look it up. That is a judgement call and nothing enforces it.