The string comes from a generated lookup table in `library/error.c`, built from the `#define`s in the public headers. A caller never gets a string directly; it has to pass the code to `mbedtls_strerror()`.

**Runtime path**

```
caller: ret = mbedtls_xxx(...)   // ret < 0, e.g. -0x3E80
   │
   ▼
mbedtls_strerror(ret, buf, buflen)            library/error.c:792
   ├─ buflen == 0 → return; else memset(buf, 0)
   ├─ ret = -ret                              (sign dropped)
   ├─ high = ret & 0xFF80 → mbedtls_high_level_strerr(ret)
   │     hit  → buf = "PK - ..."
   │     miss → buf = "UNKNOWN ERROR CODE (XXXX)"
   │     if high code is SSL fatal alert → return early
   ├─ low  = ret & ~0xFF80
   │     low == 0 → return (high-only code, done)
   │     else append " : " then mbedtls_low_level_strerr(ret)
   │     miss → "UNKNOWN ERROR CODE (XXXX)"
   ▼
buf holds a NUL-terminated, possibly truncated string
```

The bit layout is in `include/mbedtls/error.h:18-40`: a 16-bit code is a sign bit, a 3-bit high-level module ID, a 5-bit module-specific code, and a 7-bit low-level code. A PK error like `-0x3E80` falls entirely in the high-level half, so it gets the high-level string only. A code like `-0x0002` is low-level only. A combined code gets both strings joined with `" : "`.

The two lookup functions are `mbedtls_high_level_strerr` (`library/error.c:174`) and `mbedtls_low_level_strerr` (`library/error.c:537`). Each is a `switch` over `case -(MBEDTLS_ERR_X):` with `return "MODULE - description"`. Both sit under `#if defined(MBEDTLS_<MOD>_C)` guards, so the table only contains modules the build enables. When `MBEDTLS_ERROR_C` is off, `error.c:867` provides a stub that just writes an empty string.

**Where the table comes from**

`library/error.c` is generated, not hand-written. `scripts/data_files/error.fmt` is the template, and `scripts/generate_errors.pl` fills it in. The Makefile rule at `library/Makefile:355-360` regenerates it whenever a header changes. `tests/scripts/check-generated-files.sh:135` checks that the committed file matches the generator's output.

The script scans every `include/mbedtls/*.h` (excluding config headers) for this pattern:

```c
/** Doc sentence.  */            // or  /*!< Doc sentence. */ after the define
#define MBEDTLS_ERR_FOO_BAR  -0x1234
```

It takes the description from either the `/** */` comment before the define or the `/*!< */` comment after it, and dies if neither or both exist. It also dies on duplicate values.

**What a contributor has to do to add a new error code**

1. **Pick a value.** Choose an unused value in the right segment of the layout in `include/mbedtls/error.h`. Low-level codes and high-level codes use different ranges, and a code with the wrong bits lands in the wrong switch.
2. **Add the define** in the module's public header, `include/mbedtls/<module>.h`. Use the form `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....`, with exactly one doc comment, either before or after. Document it in the same style as its neighbours.
3. **Check the module is known to the generator.** `scripts/generate_errors.pl` has hard-coded `@low_level_modules` and `@high_level_modules` lists (lines ~20–30). A new module name fails with `Do not know how to handle: ...`. A new module also needs its `MBEDTLS_<X>_C` guard mapped, and its header name is derived from the module name in lowercase, with a few special cases. Do this in the script, not by hand-editing `error.c`.
4. **Regenerate.** Run `make -C library error.c`, or the Perl script from the repo root. Commit the regenerated `library/error.c` with the header change. Do not hand-edit `error.c`; the next regeneration overwrites it and the generated-files check will fail.
5. **Test it.** `tests/suites/test_suite_error.function` has an `error_strerror(code, expected)` case that calls `mbedtls_strerror` and compares the string. Add a `.data` line for the new code first and watch it fail, then regenerate and see it pass. I did not open the `.data` file, so I'm not sure of its exact entry format.

I did not run the generator or the test suite here, so the steps above come from reading the script and Makefile, not from a run.