The short answer: mbedtls does not verify constant-time behaviour at the instruction level. It shapes the code so the compiler has little room to introduce branches, uses inline assembly where the C alone isn't trusted, and checks results with Valgrind-based tests. The repo's own SECURITY.md says compilers can still introduce timing leaks.

**How it's enforced**

The core is `library/constant_time_impl.h`, which builds every operation from bitwise ops on a `mbedtls_ct_condition_t` mask (all-ones or zero) rather than `if`:

- **Opacity.** `mbedtls_ct_compiler_opaque()` (`constant_time_impl.h:85`) hides a value from the optimizer. With `MBEDTLS_CT_ASM` it emits an empty `asm volatile("" : [x] "+r" (x))`, so the compiler can't reason about the value. Without it, it returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` zero (`constant_time.c:29`).
- **Selection.** `mbedtls_ct_if()` (`constant_time_impl.h:205`) computes `(cond & if1) | (~cond & if0)`. It has hand-written asm variants for AArch64, ARM (Thumb `ands/mvns/orrs`), x86_64 and x86, each guarded by `MBEDTLS_CT_*_ASM` and `MBEDTLS_CT_SIZE_32/64`. The portable C fallback is the same mask expression, with `compiler_opaque` on the condition.
- **Comparisons.** `mbedtls_ct_uint_ne` XORs the two operands and turns the nonzero result into a mask. `mbedtls_ct_uint_eq` is its negation.
- **Volatile reads.** `mbedtls_ct_memcmp` (`constant_time.c:67`) reads both buffers through `volatile` pointers and ORs the XORs together, so the function always reads every byte and never exits early. The final bit-twiddle keeps the sign-cast well-defined.

Above these primitives, the code is written as straight-line loops with masks. Example: `mbedtls_mpi_core_lt_ct` (`bignum_core.c:133`) scans every limb, using `done` and `ret` masks instead of breaking early. `mbedtls_ct_memcpy_if` (`constant_time.c:169`) always reads both sources and selects with masks.

**If the compiler can't support it**

The asm paths are selected by preprocessor gates: `MBEDTLS_HAVE_ASM` plus `__GNUC__` or `__ARMCC_VERSION`, and for ARM, `__arm__`/`__thumb__`. If none apply, `MBEDTLS_CT_ASM` is undefined and the code uses the portable C path. Two things are weaker there:

- The barrier is `x ^ volatile_zero` rather than an empty asm, which hides the value less strongly.
- Nothing forces branch-free codegen. The C is branch-free in source, but the compiler may still insert branches.

I did not find a build-time error or warning for unsupported targets in the index, so I can't say the fallback is silent. The SECURITY.md caveat says Mbed TLS treats exploitable timing leaks that appear with a common compiler as vulnerabilities, and that compilers can introduce such leaks in code meant to be constant-time.

**Testing**

`test_with_valgrind_constant_time` in `tests/scripts/components-configuration-crypto.sh` runs a small set of dedicated constant-time tests under Valgrind. The config gate symbols `CT_VALGRIND` and `CT_MEMSAN` also appear in the index, which suggests memory-checker-based checks, but I did not confirm their purpose.

**How far it reaches**

| Area | Where | Use of the CT layer |
|---|---|---|
| Core helpers | `library/constant_time*.{c,h}`, public `include/mbedtls/constant_time.h` | Primitives: `mbedtls_ct_memcmp`, `mbedtls_ct_memcpy_if`, `mbedtls_ct_zeroize_if`, `mbedtls_ct_memcpy_offset` |
| Bignum | `library/bignum_core.c`, `bignum.c`, `bignum_internal.h` | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_lt_mpi_ct`, `mbedtls_mpi_gcd_modinv_odd` (the modular inverse is a CT wrapper), `mbedtls_ct_mpi_uint_if` |
| RSA | `library/rsa.c` | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` (Bleichenbacher-oracle hardening; reads the whole buffer, masks the padding result) |
| TLS record MAC | `library/ssl_msg.c` | `mbedtls_ct_hmac` computes HMAC with a cloned hash context so the work is the same for every padding length |
| Base64 | `library/base64.c` | `mbedtls_ct_base64_enc_char`, `mbedtls_ct_base64_dec_value` |
| Third-party | `3rdparty/p256-m` | Its own constant-time claims: Fermat inversion, and `MUL64_IS_CONSTANT_TIME` for platforms with a constant-time 32x32→64 multiply |

Gaps the index does show: the PSA transition doc says PSA has no equivalent of these utilities, and the MAC comparison guidance in `docs/psa-transition.md` tells integrators to use `mbedtls_ct_memcmp` by hand. So constant-time discipline is applied per call site in the legacy code, not as a library-wide property. I did not check every module, so this table covers only the call sites the index found.