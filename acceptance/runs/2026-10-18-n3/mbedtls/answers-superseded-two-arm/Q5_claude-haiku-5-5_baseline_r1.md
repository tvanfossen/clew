**Short answer:** Mbed TLS does not prove constant-time behaviour at the instruction level. It makes branch-free code the default, adds inline assembly on the main targets to stop the compiler from undoing that, and checks the result dynamically with Valgrind and MSan. On a compiler without the assembly it falls back to plain C, with no warning and no proof. The facility covers a lot of the secret-handling code, but not everything, and some functions are documented as not constant-time.

**1. How it is enforced at the instruction level**

- **Core primitives** live in `library/constant_time_impl.h`, with declarations in `library/constant_time_internal.h`. Everything is built from bit masks. A condition is an all-ones or all-zeros word (`mbedtls_ct_condition_t`), and `mbedtls_ct_if` selects with `and`/`or`/`not`, not with `?:` or `if`.
- **Assembly path** is selected in `constant_time_impl.h` (around lines 25–45). `MBEDTLS_CT_ASM` is set only when `MBEDTLS_HAVE_ASM` is defined and the compiler is GCC-compatible (`__GNUC__`, which includes Clang). Per-architecture macros then pick the code: `MBEDTLS_CT_ARM_ASM`, `MBEDTLS_CT_AARCH64_ASM`, `MBEDTLS_CT_X86_64_ASM`, or `MBEDTLS_CT_X86_ASM`. The asm uses hand-picked instructions (`neg`/`orr`/`asr` for the mask, `sar` for sign extension, and so on) with `asm volatile`, so the compiler cannot rewrite them into branches or conditional moves.
- **Plain-C fallback** is used on other architectures, and on compilers that are not GCC-compatible (e.g. MSVC). It relies on `mbedtls_ct_compiler_opaque()`, which XORs the value with `mbedtls_ct_zero`, a `volatile` global in `library/constant_time.c` (line 29). The compiler cannot prove the value, so it cannot fold the operation. The header's own comment says this path is "observed" to be constant-time on recent gcc, clang and MSVC as of May 2023. That is an observation, not a guarantee.
- **Memory operations** (`mbedtls_ct_memcmp`, `mbedtls_ct_memcpy_if`, `mbedtls_ct_memcpy_offset`, `mbedtls_ct_memmove_left`, `mbedtls_ct_zeroize_if`) read through `volatile` pointers so the compiler must touch every byte. `memcmp` ORs all differences rather than exiting early. `memcpy_if` does a full read of both sources and masks.

**2. What happens on a compiler that cannot support it**

- No hard failure. If `MBEDTLS_HAVE_ASM` is off, or the compiler is not GCC-compatible, `MBEDTLS_CT_ASM` is undefined and the C fallback is compiled. Nothing warns the user.
- A specific case: on 32-bit Thumb-1, the asm path is restricted by `RESTORE_ASM_SYNTAX` and register constraints. Older GCC (< 11) gets a `.syntax divided` restore to avoid breaking other asm.
- The fallback is weaker. Nothing stops the compiler from emitting a branch in the C path; it only makes that unlikely. The test suite exercises it under the `valgrind_constant_flow_no_asm` CI component, which unsets `MBEDTLS_HAVE_ASM`.

**3. How far the facility reaches**

Call counts of `mbedtls_ct_` in `library/` (rough, by file): `rsa.c` 37, `bignum_core.c` 32, `cipher.c` 30, `bignum.c` 26, `ssl_msg.c` 24, `base64.c` 21, `psa_crypto.c` 9, `ssl_tls12_server.c` 8, `nist_kw.c` 4, `psa_crypto_cipher.c` 4, and one each in `ccm.c`, `gcm.c`, `chachapoly.c`, `cmac.c`, `ssl_cookie.c` and others.

Where it is used:
- **Bignum core:** `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_uint_le_mpi`, the constant-time GCD/modular inverse for odd moduli (`bignum_core.c` around 1054 onward), and the zero check on the RSA/ECC paths.
- **RSA PKCS#1 v1.5 decoding:** `mbedtls_ct_memmove_left` and `mbedtls_ct_zeroize_if`, both gated on `MBEDTLS_PKCS1_V15`.
- **TLS record/CBC:** `ssl_msg.c` for padding and MAC handling; `ssl_tls12_server.c` for RSA premaster checks.
- **AEAD tag checks:** `gcm.c`, `ccm.c`, `chachapoly.c`, `cipher.c`, `nist_kw.c` compare tags with `mbedtls_ct_memcmp`, with comments "Check tag in constant-time".
- **Base64 decoding** (`base64.c`), which handles secret data.
- **PSA:** `psa_crypto.c` and friends route some comparisons through the same primitives.

Where it does not reach, and the code says so:
- `ecp.c` `mbedtls_ecp_mul_shortcuts` (around 2734) is explicitly "NOT constant-time". It short-circuits m = 0, 1, −1. `mbedtls_ecp_muladd_restartable` (around 2769) is also marked not constant-time.
- `bignum.c` around 302: `mbedtls_mpi_copy` is "not constant-time" and may drop leading zeros.
- `bignum.c` around 1239: a zero shortcut in multiplication that "reduces but does not eliminate side channels".
- `bignum.c` around 1621 and `bignum_core.c` around 760/838: modular exponentiation is "not constant time with respect to the exponent" in parts, and some windowing reveals the exponent.
- `ecp.c` around 2020 has a table-read comment about thwarting cache timing, which is a different mitigation from the branch-free arithmetic.
- The public `mbedtls_ct_memcmp` header says it is "not constant-time w.r.t. n", so length leaks are accepted.

**4. How it is verified**

Verification is dynamic, not static, so it can miss things:
- `tests/suites/test_suite_constant_time*.function` (and the `*constant_time*.data` files) mark secrets with `TEST_CF_SECRET` and public values with `TEST_CF_PUBLIC`. Under Valgrind or MSan (with `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` or `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN`), any branch or address that depends on a secret is reported as uninitialised-value use. CI components are in `tests/scripts/components-sanitizers.sh` and `components-configuration-crypto.sh`.
- There are separate CI runs with the asm path (`test: valgrind asm constant_time`) and with `MBEDTLS_HAVE_ASM` unset.
- Limits: this checks the actual test inputs only. It does not check the compiler's output for every path, the timing of caches or the CPU, or the non-asm code under every optimisation level. The `framework/` submodule (where `test/constant_flow.h` lives) is empty in this checkout, so I could not read the macro definitions. I inferred their behaviour from the test code and CI comments.

**Bottom line:** the guarantee is "branch-free C plus masked asm on the main targets, checked by Valgrind/MSan on test inputs." It is not a formal guarantee. Unsupported compilers silently get the weaker C fallback. Several bignum and EC routines are explicitly outside the facility.