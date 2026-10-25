**Short answer:** a negative return value becomes text through `mbedtls_strerror()`, which splits the code into a high-level part and a low-level part and looks each one up in a switch table in `library/error.c`. Adding a new string means adding a define in the module header and a `case` in that switch. The index shows the table is marked auto-generated, but it does not contain the generator, so I can't confirm the regeneration step.

**Lookup path**

```
caller: ret = -0x6C80 (negative)
   │
   ▼
mbedtls_strerror(ret, buf, buflen)          library/error.c:792
   ├─ buflen == 0 → return; memset(buf, 0)
   ├─ ret = -ret                             (sign stripped)
   ├─ high = ret & 0xFF80
   │    └─ mbedtls_high_level_strerr(ret)   error.c:174  switch on module id
   │         (fatal SSL alert → return here, skip low level)
   ├─ low  = ret & ~0xFF80
   │    └─ mbedtls_low_level_strerr(ret)    error.c:537  switch on module code
   └─ if both present: "HIGH : LOW" concatenated
      unknown code → "UNKNOWN ERROR CODE (%04X)"
```

- **Sign:** the switch cases are written as `-(MBEDTLS_ERR_xxx)`, so the function negates the input once up front and matches positive magnitudes.
- **Two layers:** the bit layout is documented in `include/mbedtls/error.h` (around line 165, the `MBEDTLS_ERR_ERROR_GENERIC_ERROR` doc). The high-level part is a 3-bit module ID; the low-level part is a 7-bit code. A single returned value can carry both, which is why a message can read `SSL - ... : ...`.
- **Output:** the result is always NUL-terminated and truncated to `buflen`. The caller gets a formatted string in its own buffer, not a pointer to static text.
- **Build gating:** the tables are wrapped in `#if defined(MBEDTLS_<MODULE>_C)` blocks, and the whole file is gated on `MBEDTLS_ERROR_C`. With `MBEDTLS_ERROR_C` off, the function is a stub. A second definition at `error.c:867` sits under that gate's other branch. I did not read its body, so I can't say exactly what it returns.
- **Public accessors:** `mbedtls_high_level_strerr()` and `mbedtls_low_level_strerr()` are also public, declared in `error.h` at lines 180 and 195.

**What a contributor has to do for a new code**

1. Add `MBEDTLS_ERR_<MODULE>_<NAME>` to the module's public header with a value that fits the bit layout. Check the code table in `error.h` for free slots, since the table lists which numbers are already taken. Note that `error.h` documents the high-level IDs and the module low-level ranges separately, so pick the slot under the right module.
2. Add a `case -(MBEDTLS_ERR_<MODULE>_<NAME>): return( "<MODULE> - <description>" );` inside the matching `#if defined(MBEDTLS_<MODULE>_C)` block in `library/error.c`. The module ID block for high-level codes lives in `mbedtls_high_level_strerr`, and the low-level block lives in `mbedtls_low_level_strerr`. Keep the `MODULE - text` prefix format used in the existing entries.
3. If the file's `Begin/End Auto-Generated Code` markers apply, make the change in whatever generates them rather than hand-editing. The index has no `generate_errors` symbol and does not index `.pl` files, so I can't name that generator. A search of the repo's docs found nothing on how to run it. Check the repo's `scripts/` directory or its contributing docs for the exact command.
4. Add a `ChangeLog.d` entry. `ChangeLog.d/00README.md` describes the format, and the repo's docs say new error codes are part of the public API.

**Gaps:** the index can't show the generator for the `error.c` tables, the body of the `error.c:867` definition, or whether any test checks that every `MBEDTLS_ERR_*` has a string. Those would need a look at the source tree outside this index.