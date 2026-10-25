## How a negative code becomes a string

The path runs through `library/error.c`, which is generated, not hand-written.

```
mbedtls_strerror(ret, buf, buflen)            error.c:792
 ├─ buflen==0 → return; zero buf; ret = -ret
 ├─ ret & 0xFF80 ?  → mbedtls_high_level_strerr(ret)   high 3 bits (module)
 │                    └─ switch on case -(MBEDTLS_ERR_X_...) → "MODULE - text"
 │                    (miss → "UNKNOWN ERROR CODE (XXXX)")
 │                    SSL fatal alert → return here, skip low level
 ├─ ret & ~0xFF80 ?  → append " : " then
 │                    mbedtls_low_level_strerr(ret)        low 7 bits
 │                    └─ switch → "MODULE - text"
 └─ write into buf (snprintf)
```

1. The caller's negative value is negated, then split by the 16-bit layout described in `include/mbedtls/error.h`: a 3-bit high-level module ID (`0xFF80` mask) and a 7-bit low-level code (`~0xFF80`).
2. Each half goes through a large `switch` in `error.c`. Each `case -(MBEDTLS_ERR_...)` returns a `"MODULE - description"` string.
3. A high-level and a low-level error in one code are joined as `"HIGH : LOW"`.
4. Unmatched codes print `UNKNOWN ERROR CODE (%04X)`.
5. If `MBEDTLS_ERROR_C` is off, the dummy at `error.c:867` only blanks the buffer.

The `switch` bodies are between `Begin/End Auto-Generated Code` markers, filled from `scripts/data_files/error.fmt` by `scripts/generate_errors.pl`.

## Adding a new error code

1. **Define it** in the module's public header, for example `include/mbedtls/cipher.h`: `#define MBEDTLS_ERR_<MOD>_<NAME> -0xNNNN`. Pick a free value in that module's range from the table in `error.h`.
2. **Document it** with exactly one description, either a `/** ... */` block before the define or a `/*!< ... */` after it. The generator dies if both or neither are present, and it discards `\name`-style blocks.
3. **Check the module.** The module must be listed in `@low_level_modules` or `@high_level_modules` in `generate_errors.pl`, otherwise it exits with "Do not know how to handle". A new module also needs its header to appear in the include mapping, or the generator fails with "has not been included".
4. **Regenerate.** Run `scripts/generate_errors.pl` from the repo root, or `make` in `library/` (the `error.c:` rule). Don't edit `error.c` by hand. `tests/scripts/check-generated-files.sh` rebuilds it and fails on drift. `scripts/bump_version.sh` also regenerates it.
5. **Test and log.** Add a case to `tests/suites/test_suite_error.function`, and add a ChangeLog entry if the repo's convention requires one. I did not read those two files, so check them before relying on this step.

I did not run the generator or the tests here. I read the generator, `error.c`, `error.h` and the build rules, and the flow above comes from that reading.