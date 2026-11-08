**Short version:** `mbedtls_strerror()` in `library/error.c` splits the code into a high-level part and a low-level part, looks each up in a generated `switch`, and concatenates the results. To add a new string, you add the error macro to its module header, then add a `case` to the generated `switch` in `library/error.c`. The index doesn't show how the generator script orders or validates entries, so the second step needs checking against the script itself.

**The lookup path**

```
caller: ret = -0x0021 (negative)
  │
  ▼
mbedtls_strerror(ret, buf, buflen)              library/error.c:792
  ├─ buflen == 0 → return; else memset(buf, 0)
  ├─ ret = -ret                                  (sign is dropped)
  ├─ if (ret & 0xFF80):                          high-level part present
  │    mbedtls_high_level_strerr(ret)            library/error.c:174
  │      switch on (ret & 0xFF80), one case per module
  │      e.g. "CIPHER - Authentication failed …"
  │    NULL → "UNKNOWN ERROR CODE (%04X)"
  │    if high == MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE → return (no low-level text)
  ├─ use_ret = ret & ~0xFF80; if 0 → return
  ├─ if buf already has text → append " : "
  └─ mbedtls_low_level_strerr(ret)               library/error.c:537
       switch on (ret & ~0xFF80), one case per module
       e.g. "AES - Invalid input data"
       NULL → "UNKNOWN ERROR CODE (%04X)"
```

Key points:

- **Public entry point:** `mbedtls_strerror()` is declared in `include/mbedtls/error.h:165`. It writes a null-terminated string and truncates if the buffer is too small.
- **Two-part code:** the high-level part is the mask `0xFF80` and the low-level part is everything outside it. A single error such as `CIPHER - …` plus `AES - …` can therefore print as `CIPHER - … : AES - …`.
- **Fatal SSL alerts:** when the high-level part is `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE`, the function returns early and skips the low-level lookup.
- **Gating:** both lookup functions sit under `MBEDTLS_ERROR_C` (`include/mbedtls/mbedtls_config.h:2907`, default on). Each module's `case` lines are wrapped in `#if defined(MBEDTLS_<MODULE>_C)`. A code whose module is compiled out has no string in that build and falls through to `UNKNOWN ERROR CODE`.
- **Generated code:** both `switch` bodies are marked `Begin Auto-Generated Code` and produced by `scripts/generate_errors.pl` (usage: `generate_errors.pl include_dir data_dir error_file`). Do not hand-edit the switches. The index holds no symbols for the script itself, so I could not read how it chooses case order or what it validates.

**What a contributor does to add a new error**

1. Pick the module header in `include/mbedtls/` (e.g. `aes.h`) and add `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x00XX` in that module's range. The index shows the existing pattern, e.g. `MBEDTLS_ERR_AES_BAD_INPUT_DATA` is `-0x0021`, expanded in `include/mbedtls/aes.h:50`.
2. Add a description entry for that code in the generator's data source. The index does not show where that lives, so check `scripts/generate_errors.pl` and its `data_dir` input.
3. Regenerate `library/error.c` with the script, not by hand.
4. Verify through pre-commit as the repo's `AGENTS.md` requires. Check that the new code translates to a string and not `UNKNOWN ERROR CODE`.

I could not verify step 2 or the exact pre-commit hook names from the index alone. The index has the `error.h` and `error.c` pieces but nothing from the generator's internals or the `data_dir` inputs.