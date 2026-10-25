**Short answer:** constant-time behaviour is enforced by construction, not by a checker. Branch-free masks and volatile barriers are written into C, with hand-written assembly on a few targets. Where that assembly is unavailable, a plain C fallback runs with no build-time check. The facility reaches the secret-dependent paths in bignum, RSA, EC, TLS record MAC verification and base64. The index cannot show the emitted machine code, so the instruction-level claims below come from reading the source, not from disassembly.

**1. How it is enforced at the instruction level**

Everything sits on one representation: `mbedtls_ct_condition_t` is an all-ones or all-zeros mask, and the helpers combine masks with bitwise operations (`library/constant_time_impl.h`).

- **Mask generation.** `mbedtls_ct_bool(x)` turns any non-zero `x` into an all-ones mask without a branch. The AArch64 path is `neg; orr; asr #63`. The x86-64 path is `mov; neg; or; sar $63`. The generic C path uses `-xo | -(xo>>1)` and a shift.
- **Hiding values from the optimiser.** `mbedtls_ct_compiler_opaque(x)` is an empty `asm volatile` barrier when assembly is enabled. Otherwise it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global (`library/constant_time.c:29`). Its stated purpose is that the compiler cannot prove any condition value, so it cannot turn a mask back into a branch.
- **Forced full memory reads.** `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers and never exits early. Its comment says why: without `volatile`, the compiler may emit an early exit once `diff` is non-zero. Its length `n` is public.
- **Fixed iteration counts.** `mbedtls_mpi_core_lt_ct` (`library/bignum_core.c:133`) walks every limb, with `done` and `ret` carried as masks. `mbedtls_mpi_core_check_zero_ct` force-reads each limb through a `volatile` pointer.
- **Fixed memory access patterns.** `ecp_select_comb` (`library/ecp.c:2010`) reads the whole precomputed table and selects with `MPI_ECP_COND_ASSIGN`, so the access pattern does not depend on the secret index.

**2. A compiler that cannot support it**

- Assembly is gated by `MBEDTLS_CT_ASM`, which requires `MBEDTLS_HAVE_ASM` and either `__GNUC__` or `__ARMCC_VERSION` (`library/constant_time_impl.h:40-52`). Per-architecture variants are selected by `__aarch64__` and the `MBEDTLS_CT_*_ASM` macros. Word width is selected by `MBEDTLS_CT_SIZE_32` or `_64`.
- Anything else falls through to the C fallback. The header comment says that as of May 2023, trunk clang, gcc and MSVC did not turn that fallback into branches or conditional instructions. That is a point-in-time observation, not a guarantee.
- **Nothing fails the build.** The only hard `#error` in the constant-time code is in `mbedtls_ct_memcmp`, and it fires only when `int` is narrower than 32 bits.
- `SECURITY.md` ("Caveats") says compilers can introduce timing side channels into code meant to be constant-time, and that the library uses standard C "except with known compilers". The index holds only part of that passage, so I cannot quote the rest.
- `3rdparty/p256-m` has its own variant. Its README says the constant-time multiplication path depends on the `MUL64_IS_CONSTANT_TIME` symbol, and that some features need GCC extended asm.

**3. How far it reaches**

Public API: `mbedtls_ct_memcmp` in `include/mbedtls/constant_time.h`, `mbedtls_mpi_lt_mpi_ct` in `bignum.h`, and `mbedtls_mpi_gcd_modinv_odd` as a wrapper over constant-time code.

Internal users the index shows:

| Location | Function | What it hides |
|---|---|---|
| `library/ssl_msg.c` | `mbedtls_ct_hmac` | TLS record MAC over a secret-length range; clones the hash and finishes at every length (padding-oracle defence). Gated on `MBEDTLS_SSL_SOME_SUITES_USE_MAC`. |
| `library/rsa.c` | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` | PKCS#1 v1.5 unpadding, to resist Bleichenbacher-style oracles. |
| `library/ecp.c` | `ecp_select_comb` | Comb-method table lookup during EC scalar multiplication. |
| `library/base64.c` | `mbedtls_ct_base64_dec_value` | Base64 decoding without table lookups indexed by the secret byte. |
| `library/constant_time.c` | `mbedtls_ct_memcpy_if`, `_offset`, `memmove_left`, `memcmp_partial` | Conditional copies and shifts. |
| `library/bignum.c` | `mbedtls_ct_mpi_sign_if` | Conditional sign selection. |

A name search for `ct_` returned exactly 60 rows, which is the limit I set, so there may be more. I did not enumerate every caller.

**Limits**

- Documentation says there is no equivalent in the PSA API (`docs/psa-transition.md`). PSA-path code that compares MACs must call `mbedtls_ct_memcmp` by hand.
- `SECURITY.md` says Mbed TLS makes no guarantee against local non-timing side channels.
- The one dynamic check the index shows is `test_with_valgrind_constant_time` in `tests/scripts/components-configuration-crypto.sh`. It runs a small set of constant-time tests under Valgrind. I could not confirm from the index whether CI runs it on every compiler.