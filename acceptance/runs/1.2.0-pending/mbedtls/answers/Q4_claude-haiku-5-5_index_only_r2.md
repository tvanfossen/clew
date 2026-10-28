The path from a negative return to a string is a single translation function plus two generated lookup tables, and a contributor adds a message by editing the module header and rebuilding, not by editing `error.c`.

```
ret = -0x0020            (e.g. MBEDTLS_ERR_AES_INVALID_KEY_LENGTH, aes.h:44)
  │
  ▼
mbedtls_strerror(ret, buf, buflen)            library/error.c:792
  │  memset buf to 0; if buflen == 0 return
  │  ret = -ret                              (sign flipped, now 0x0020)
  │
  ├─ ret & 0xFF80 ?  ──yes──▶ mbedtls_high_level_strerr(ret)   error.c:174
  │                             "AES - ..." (module name)
  │                             unknown → "UNKNOWN ERROR CODE (%04X)"
  │                             SSL fatal alert → return here, no low-level part
  │
  ├─ use_ret = ret & ~0xFF80 ; 0 → return
  │
  ├─ buf already has text? append " : " (only if 5+ bytes remain)
  │
  └─ mbedtls_low_level_strerr(ret)             error.c:537
                                "Invalid key length" style detail
                                unknown → "UNKNOWN ERROR CODE (%04X)"
```

Some details from the bodies:

- **Two halves.** The high bits (`0xFF80`) identify the module and the low bits (`~0xFF80`) identify the specific error. Both helpers are passed the full negated value and each masks its own part.
- **Output.** A code with both parts reads like `"<MODULE> - <high> : <low>"`. Every write goes through `mbedtls_snprintf`, so the result is truncated to `buflen` and always null-terminated.
- **Module gating.** Each `case` sits inside `#if defined(MBEDTLS_<MODULE>_C)`, so a string disappears from the table when its module is compiled out. `mbedtls_strerror` itself is gated by `MBEDTLS_ERROR_C`.
- **Generated, not hand-written.** Both helpers are inside the "Begin Auto-Generated Code" block. `library/CMakeLists.txt:134` runs `scripts/generate_errors.pl` at build time over the headers in `include/mbedtls` and `scripts/data_files/error.fmt`, producing the build-dir `error.c`. Any hand edit to the checked-in `library/error.c` is overwritten.

**To add a new message:**

1. Add `#define MBEDTLS_ERR_<MODULE>_<NAME> -0x....` to the module's public header, with the description in the comment the generator reads. Pick a value inside that module's band. I did not confirm the band rules, because the generator is not in the index.
2. Rebuild so the generator picks it up. Don't edit `library/error.c`.
3. If the code should also map to a PSA status, update `mbedtls_to_psa_error`. The index shows it references existing codes like `MBEDTLS_ERR_AES_INVALID_KEY_LENGTH`.
4. Check the output with `programs/util/strerror.c` (`strerror <code>`), which prints the string for a decimal or `-0x` hex code.
5. Add a ChangeLog.d entry. `BRANCHES.md` treats a new error condition for a previously undocumented function as a compatibility-relevant change.

**Limits of this answer.** The index holds the generated `error.c` and the header macros, but not `generate_errors.pl`, `error.fmt`, or the CMake rule's inputs. So the exact comment format the generator parses, the value bands per module, and whether the PSA mapping is generated are unverified. Read the Perl script before writing the header comment.