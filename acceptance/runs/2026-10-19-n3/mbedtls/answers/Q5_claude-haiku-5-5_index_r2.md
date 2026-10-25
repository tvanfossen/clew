**Short answer:** constant-time behaviour in mbedtls is a convention enforced by coding style, not by the compiler. Branch-free primitives are built on masks, and hand-written inline assembly pins the instruction sequence on the common targets. On a compiler or target without that assembly, the code silently falls back to portable C. Only about two dozen library files use the primitives, and the rest of the library is not covered by this facility.

**1. How it is enforced at the instruction level**

- **Masks, not booleans.** `mbedtls_ct_condition_t` is an all-ones or all-zeros word, `uint32_t` or `uint64_t` depending on pointer size (`library/constant_time_internal.h:67-83`). Everything is built from it:
  - `mbedtls_ct_bool` turns a value into a mask with `neg / or / sar` (`constant_time_impl.h:120-203`).
  - `mbedtls_ct_if` selects with `(c & a) | (~c & b)` (`:205-269`).
  - `mbedtls_ct_uint_lt` uses the sign-bit trick (`:271-380`). `eq`, `ne`, `ge` and so on are derived from `lt` and `ne` (`:382-511`).
- **Inline asm pins the sequence.** On AArch64, 32-bit Arm/Thumb, x86-64 and x86-32, the core `bool`, `if` and `lt` primitives are `asm volatile` blocks. The optimiser cannot turn these into a branch or a cmov it chooses itself (`constant_time_impl.h:130-348`).
- **Hiding values from the optimiser.** `mbedtls_ct_compiler_opaque` is an empty `asm volatile` with a `+r` constraint on the asm path (`:85-93`). This stops the compiler from proving a secret's value and folding the mask logic away.
- **Memory access.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers and always scans all `n` bytes, so there is no early exit (`library/constant_time.c:67-116`). `mbedtls_ct_memcpy_if` always reads both sources and blends them with masks (`:169-212`).

**Limit:** `volatile` and asm guarantee the emitted instructions, not the microarchitecture. Cache and timing side channels are outside what this code can control.

**2. What happens on a compiler that cannot support it**

The asm gate is at `constant_time_impl.h:40-52`:

```
MBEDTLS_HAVE_ASM && __GNUC__ && (not armcc5 || armcc >= 6)  →  MBEDTLS_CT_ASM
```

| Situation | What is used |
|---|---|
| GCC or Clang, `MBEDTLS_HAVE_ASM`, supported arch | Arch-specific asm (`MBEDTLS_CT_*_ASM`) |
| GCC or Clang, arch with no hand-written block (e.g. RISC-V) | `MBEDTLS_CT_ASM` is set, but `bool`/`if`/`lt` fall to plain C; `compiler_opaque` still uses the empty asm |
| `MBEDTLS_HAVE_ASM` undefined (the documented way to disable asm) | Pure C fallback. `mbedtls_ct_zero` is a `volatile` global (`constant_time.c:23-30`), and `compiler_opaque` becomes `x ^ mbedtls_ct_zero` |
| MSVC, armcc5 | Same pure C fallback |

Key points:
- **No build error or warning.** `check_config.h` has no constant-time check. The only hard error is `mbedtls_ct_memcmp` on a platform with `int` narrower than 32 bits (`constant_time.c:99-105`).
- **The C fallback is empirical.** The header comment says it "has been observed to be constant-time" on recent gcc, clang and MSVC as of May 2023 (`constant_time_internal.h:~60-66`). Nothing guarantees that a future optimiser keeps it that way.

**3. How far it reaches**

Public surface: `include/mbedtls/constant_time.h` exports only `mbedtls_ct_memcmp`. The bignum headers add `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_lt_mpi_ct`, `mbedtls_mpi_core_check_zero_ct` and `mbedtls_mpi_gcd_modinv_odd`. Everything else is internal.

Call sites found by grep for `mbedtls_ct_*(`:

| File | Approx. call count | Role |
|---|---|---|
| `rsa.c` | 25 | PKCS#1 v1.5 unpadding (`:420` onward) |
| `bignum_core.c` / `bignum.c` | 21 / 18 | Constant-time MPI comparison and zero checks |
| `cipher.c` | 20 | CBC padding removal |
| `ssl_msg.c` | 17 | TLS CBC padding check (`:1916-1978`), `mbedtls_ct_hmac` (`:187`), MAC compare (`:1798`) |
| `base64.c` | 10 | Constant-time base64 encode/decode |
| `psa_crypto.c` | 5 | Tag and hash compares via `mbedtls_ct_memcmp` (e.g. `:2514`, `:3013`) |
| `ssl_tls12_server.c` | 7 | Premaster/RSA handling |
| `nist_kw.c` | 4 | Key-wrap integrity check |
| `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `ssl_cookie.c` | 1 each | Tag comparisons, mostly |

Not covered, as far as the grep shows:
- `ecp.c`, `aes.c` and `x509*.c` do not call the `mbedtls_ct_*` primitives. I did not audit whether their secret-dependent paths are constant-time some other way, so this is a gap in the facility, not a verified finding about those files.
- The `mbedtls_ct_memcmp` doc says it is "not constant-time w.r.t. `n`", so the length is treated as public.

**4. How it is verified**

- `tests/suites/test_suite_constant_time*.data` exercise the primitives. They use `TEST_CF_SECRET` / `TEST_CF_PUBLIC` markers, which let MSan or Valgrind flag any branch or index that depends on a secret.
- `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25-33`) runs those suites under Valgrind. It is invoked from several CI components. The `test_suite_constant_time_hmac` suite is excluded from that run through `GLOBIGNORE`, and I did not check why.
- Verification runs on the platforms CI builds, so the asm-specific and C-fallback paths are tested only where those builds run.