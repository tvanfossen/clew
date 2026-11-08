**Short answer:** the constant-time guarantee is a convention enforced by code shape plus two checks, not by the build. Nothing stops a compiler from breaking it, and the index shows no build-time refusal when the assembly path is unavailable. The facility reaches the secret-dependent parts of RSA, HMAC, bignum, base64 and NIST KW, but not the whole library.

**1. How it is enforced at the instruction level**

- **Masks, not branches.** `library/constant_time_impl.h` builds every condition as a full-width mask. `mbedtls_ct_bool(x)` yields all-ones if `x != 0`, else zero. The comparisons (`mbedtls_ct_uint_lt`, `_eq`, `_ge`, and so on) and the selectors (`mbedtls_ct_uint_if`, `mbedtls_ct_memcpy_if`) are built on it. Callers combine conditions with `mbedtls_ct_bool_and/or/not` and never write `if` on secret data.
- **Hiding the value from the optimiser.** `mbedtls_ct_compiler_opaque(x)` is the key piece. In assembly builds it is an empty `asm volatile` that ties `x` to a register. In C builds it returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a global `volatile` set to 0. The compiler cannot prove the value, so it cannot fold the mask back into a branch.
- **Hand-written assembly for four targets.** `mbedtls_ct_bool` and `mbedtls_ct_uint_lt` have AArch64, 32-bit ARM (Thumb-2 aware), x86 and x86-64 variants, each with size guards (`MBEDTLS_CT_SIZE_32` / `_64`). For example, the x86-64 `bool` is `mov; neg; or; sar $63`, which produces the mask in a few instructions with no flags-dependent jump.
- **Volatile reads for buffers.** `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers so the loop cannot exit early on the first difference. It OR-accumulates XORs and returns the result without a branch on the data. Its doc says it is not constant with respect to `n`.
- **A test hook.** `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25`) runs the `*constant_time*.data` suites under Valgrind. The index does not show how the check detects secret-dependent behaviour, so I can't say more than that.

**2. A compiler that cannot support it**

`MBEDTLS_CT_ASM` (`constant_time_impl.h:42`) is defined only when `MBEDTLS_HAVE_ASM` is on and the compiler is GCC-like or ARM Compiler (`__GNUC__` / `__ARMCC_VERSION`). Otherwise the assembly branches are skipped and the plain-C fallbacks are used. There is no `#error` or runtime warning. Two consequences follow:

- The security property silently becomes "whatever the optimiser does with the C." The C comment in `mbedtls_ct_bool` says the fallback "does not get optimised into conditional instructions or branches by trunk clang, gcc, or MSVC v19" as of May 2023. That is a dated observation, not a guarantee.
- `SECURITY.md` (Caveats) says compilers can introduce timing side channels in code meant to be constant-time, and that exploitable ones seen with a common compiler are treated as vulnerabilities. It also says Mbed TLS makes no guarantees against local non-timing side channels. I could only read part of that section.

**3. How far it reaches**

| Area | Use | Source |
|---|---|---|
| RSA PKCS#1 v1.5 decrypt | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` scans the whole buffer with masks, to resist Bleichenbacher | `library/rsa.c:420` |
| TLS record MAC | `mbedtls_ct_hmac` hashes up to the minimum length, clones the hash state, and selects the right result for each possible length, to resist padding-length timing | `library/ssl_msg.c:65` |
| Bignum | `mbedtls_mpi_safe_cond_assign`/`swap`, `mbedtls_mpi_exp_mod_optionally_safe`, `mbedtls_mpi_lt_mpi_ct`, `mbedtls_mpi_core_lt_ct`, `_check_zero_ct`, `mbedtls_mpi_gcd_modinv_odd` | `library/bignum.c`, `bignum_core.c` |
| Base64 decode | `mbedtls_ct_base64_dec_value` avoids table lookups indexed by secret characters | `library/base64.c:40` |
| NIST KW unwrap | `mbedtls_ct_memcmp_partial` compares the integrity block | `library/nist_kw.c` |
| Public API | `mbedtls_ct_memcmp` in `include/mbedtls/constant_time.h` | — |

Limits of what the index can show:

- It shows no internal callers of `mbedtls_ct_memcmp`; its only recorded caller is itself, so the index cannot say where the public function is used.
- Most other code, including the ECC layer, the non-RSA paths, the PSA drivers and the rest of the bignum code, is not shown as using these helpers.
- `3rdparty/p256-m` is a separate, self-contained implementation. Its README claims it is constant-time from the ground up. It has its own `MUL64_IS_CONSTANT_TIME` switch and uses Fermat inversion, so it does not depend on `library/constant_time*`.
- `docs/psa-transition.md` says the PSA API has no equivalent to these helpers, so PSA code must use `mbedtls_ct_*` or equivalent by hand.