**Short answer:** nothing enforces constant time at build time. The library tries to produce branch-free code through a small primitive layer, with inline assembly on the main targets and a C fallback elsewhere. Whether the output is actually constant-time is checked by tests, not guaranteed by the compiler. The facility is used across the bignum, cipher, MAC/AEAD, RSA, PSA and TLS code paths, but not uniformly.

**How it works at the instruction level**

- The primitives are in `library/constant_time_internal.h` and `library/constant_time_impl.h`. They take secret values and return a mask (all ones or zero) rather than a bool, so there is no branch. Operations include `mbedtls_ct_bool`, `mbedtls_ct_uint_lt/eq/ne`, `mbedtls_ct_if` and `mbedtls_ct_memcpy_if`.
- `mbedtls_ct_bool` is a neg/or/shift sequence that turns any nonzero value into all-ones. `mbedtls_ct_if` is a bitwise select (`(c & a) | (~c & b)`). `mbedtls_ct_uint_lt` uses a sign-bit trick and never compares directly.
- Assembly is used when `MBEDTLS_HAVE_ASM` is defined, the compiler is GCC-compatible (including Clang), and the target is Arm, AArch64, x86 or x86-64 (`constant_time_impl.h`, the `MBEDTLS_CT_*_ASM` selection near the top). The asm is `asm volatile` with explicit register constraints, which stops the compiler from rewriting the sequence into a branch.
- `mbedtls_ct_compiler_opaque()` hides values from the optimizer. With asm it is an empty `asm volatile` barrier. Without asm it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` zero the compiler cannot fold (`library/constant_time.c`).
- `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers so the compiler cannot exit early on the first mismatch (`library/constant_time.c`, near line 60).

**A compiler that cannot support it**

There is no `#error` and no build failure. If `MBEDTLS_HAVE_ASM` is off, the compiler is not GCC-like (for example MSVC or IAR), or the architecture is not one of the four asm targets (RISC-V, for example), the code silently uses the portable C path. The header says this C fallback was "observed" to be constant-time on recent gcc, clang and MSVC as of May 2023. That is an observation, not a guarantee; a future optimizer could introduce a branch. The fallback therefore gives weaker assurance, and nothing in the build tells you which path you got.

Two related constraints are enforced:
- `include/mbedtls/check_config.h` (around line 250) rejects MemorySanitizer combined with `MBEDTLS_HAVE_ASM`. Sanitizer testing requires the C path.
- `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` requires a MemorySanitizer build (check_config.h around line 247).

**How far it reaches**

About 30 library files call the `mbedtls_ct_*` API. The heaviest users are:

| Area | Files | Examples |
|---|---|---|
| RSA PKCS#1 v1.5 unpadding | `rsa.c` (~37 uses) | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` |
| Bignum core | `bignum_core.c`, `bignum.c`, `bignum_mod_raw.c` | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_uint_le_mpi` |
| Cipher padding and MAC checks | `cipher.c`, `base64.c`, `nist_kw.c`, `ccm.c`, `gcm.c`, `chachapoly.c`, `cmac.c` | padding removal, tag comparison |
| TLS record layer | `ssl_msg.c` (~24 uses), `ssl_tls12_*`, `ssl_tls13_*`, `ssl_cookie.c` | CBC padding and MAC check (`mbedtls_ct_memcmp` near lines 1798 and 2071) |
| PSA | `psa_crypto*.c`, `psa_crypto_driver_wrappers.h` | mirrors the cipher and RSA paths |

Things I did not confirm:
- `ecp.c` has no direct `mbedtls_ct_*` calls. Its constant-time behaviour, such as `ecp_select_comb`, depends on code I did not trace, so I cannot say it is covered.
- Whether the test helpers actually detect leaks on your target. The `TEST_CF_SECRET`/`TEST_CF_PUBLIC` macros come from `framework/tests/include/test/constant_flow.h`, but the `framework` submodule is empty in this checkout, so I could not read them.

**How it is verified**

- `tests/suites/test_suite_constant_time*.function` and the bignum and RSA suites mark secret inputs as undefined under Valgrind memcheck or MSan. Any secret-dependent branch or index is then reported as an error.
- `tests/scripts/components-sanitizers.sh` and `components-configuration-crypto.sh` run these builds. The `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` and `_MEMSAN` options are disabled by default.
- Most of this is testing, not design guarantees: a leak in a path the suites do not exercise would go unnoticed.