**Short answer:** the string comes from `mbedtls_strerror()` in `library/error.c`, which splits the code into a high-level part and a low-level part and looks each one up in a generated `switch`. To add a new code you define the macro in the module's header, add the module to the generator's lists if it is new, and regenerate `error.c`. Don't hand-edit `error.c`.

**Runtime path**

```
ret (negative int)
  └─ mbedtls_strerror(ret, buf, buflen)        error.c:792   (public: error.h:165)
       ├─ buflen == 0 → return; else memset(buf, 0)
       ├─ ret = -ret                             (codes are stored negated)
       ├─ ret & 0xFF80  → mbedtls_high_level_strerr(ret)   error.c:174
       │                    "CIPHER - Authentication failed …"
       │     └─ if it's MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE → return now
       ├─ ret & ~0xFF80 → mbedtls_low_level_strerr(ret)    error.c:537
       │                    "ASN1 - Out of data when parsing …"
       └─ join:  "HIGH : LOW"   (or just one part if the other is zero)
          unknown part →  "UNKNOWN ERROR CODE (%04X)"
```

- The high/low split uses the bit layout documented in `include/mbedtls/error.h` (high-level modules in the `0xFF80` bits, low-level modules in the low 7 bits).
- Each lookup is a `switch` over `case -(MBEDTLS_ERR_X):` returning a `"MODULE - description"` literal. Cases are wrapped in `#if defined(MBEDTLS_<MOD>_C)`, so a disabled module's strings are not compiled in.
- The output is written through `mbedtls_snprintf`, so it is truncated to `buflen` and always NUL-terminated.
- If `MBEDTLS_ERROR_C` is off, the dummy at `error.c:867` just writes an empty string.

**Where the switch comes from**

`library/error.c` is generated. `scripts/generate_errors.pl` does this:

1. Scans every `include/mbedtls/*.h` for `#define MBEDTLS_ERR_<NAME> -0x....` with a Doxygen description, either before the macro (`/** … */`) or after it (`/*!< … */`).
2. Takes the module name from the `MBEDTLS_ERR_<MODULE>` prefix (with a few renames such as `MPI`→`BIGNUM`) and sorts it into the `@low_level_modules` or `@high_level_modules` list at `scripts/generate_errors.pl:36-43`.
3. Writes the cases and the `#include`s into the template `scripts/data_files/error.fmt`, producing `library/error.c`.

Regeneration is wired into `library/Makefile:355-360`, `library/CMakeLists.txt:139-146`, and `scripts/make_generated_files.bat`. `tests/scripts/check-generated-files.sh:135` checks that the committed `error.c` matches the generator output.

**To add a new error code**

1. **Pick a free value.** Use an unused `-0x....` in the module's range, from the allocation table in `include/mbedtls/error.h` (around lines 37–60). The generator dies on duplicate values.
2. **Define the macro** in the module's public header, e.g. `include/mbedtls/<module>.h`:
   ```c
   /** Short description, ending without a period. */
   #define MBEDTLS_ERR_FOO_BAR    -0x0042
   ```
   Use exactly one comment, either before or after. Both, or neither, is an error. The description text becomes the user-visible string, so write it for the caller who reads it.
3. **If the module is new**, add it to the right list in `scripts/generate_errors.pl`. An unlisted module makes the generator print `Do not know how to handle` and exit 1. Add an explicit `define_name` mapping only if the `MBEDTLS_<X>_C` gate name differs from the prefix.
4. **Regenerate** through the build (`make` in `library/`, or the CMake build), or run `perl scripts/generate_errors.pl` from the repo root. Commit the regenerated `library/error.c` together with the header change.
5. **Verify** with `check-generated-files.sh`, and run the project's pre-commit gate as `AGENTS.md` describes.

**What I did not check:** I did not read `error.fmt` itself, the table of allocated ranges in full, or whether any test asserts specific error strings. Those would be the next places to look if the string needs special handling.