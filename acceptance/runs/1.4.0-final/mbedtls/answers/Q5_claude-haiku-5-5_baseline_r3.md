The facility is `mbedtls_ct_*`, and it has two layers: a set of primitives that are written to avoid branches, and an assembly layer that tries to force the compiler to keep them that way. Nothing in the build verifies the result. The verification is test-time only, and only on a few configurations.

**How it is enforced at the instruction level**

- **Interface.** `include/mbedtls/constant_time.h` exposes only `mbedtls_ct_memcmp`. The wider set (`mbedtls_ct_uint_eq`, `_lt`, `_if`, `_memcpy_if`, `_bool_or`, and so on) is internal, in `library/constant_time_internal.h`. Conditions are an opaque `mbedtls_ct_condition_t` (all-ones or zero), so a branch on a secret becomes a mask computation.
- **Opacity.** `mbedtls_ct_compiler_opaque()` (`library/constant_time_impl.h`) stops the compiler from proving a value. On the asm path it is `asm volatile("" : "+r"(x))`. On the C path it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global defined in `library/constant_time.c`.
- **Mask generation.** `mbedtls_ct_bool(x)` turns any value into all-ones or zero. On AArch64 it is `neg / orr / asr #63`, and there are hand-written variants for 32-bit Arm, x86-64 and x86. Selection (`mbedtls_ct_if`) is `and / mvn / and / orr` on AArch64, and similarly elsewhere. `mbedtls_ct_memcmp` XORs and accumulates over `volatile` reads.
- **Selection of asm.** `MBEDTLS_CT_ASM` is set only when `MBEDTLS_HAVE_ASM` is defined, the compiler is GNU-compatible (GCC or Clang, not MSVC or old armcc), and the architecture is one of the four listed. The asm is then picked per architecture and word size.

**What happens on a compiler or architecture without it**

Nothing fails. If `MBEDTLS_CT_ASM` is not defined, the code uses the plain-C versions. The C fallback relies on the `volatile` zero and on arithmetic masks, and the header's own comment says it has been "observed" to be constant-time on recent gcc, clang and MSVC as of May 2023. That is an empirical observation, not a guarantee. The header also says the asm should be the path that is used on the supported architectures.

Two more things bear on this:
- Disabling asm is a supported switch: `MBEDTLS_HAVE_ASM` can be commented out in `mbedtls_config.h`. The tests exercise this path (`component_release_test_valgrind_constant_flow_no_asm`).
- MemorySanitizer cannot be used with asm. `include/mbedtls/check_config.h` raises an `#error` if both are set, so the MSan build always uses the C path.

**How far it reaches**

- **Primitives.** `library/constant_time.c` (memcmp, PKCS#1 v1.5 padding helpers, the NIST KW comparison, and the conditional copies) and `library/constant_time_impl.h`.
- **Bignum.** `library/bignum_core.c` uses it for conditional select and compare. `library/bignum.c` references it 26 times and `library/rsa.c` 37 times.
- **Symmetric and AEAD.** `ccm.c`, `gcm.c`, `chachapoly.c`, `cmac.c`, `cipher.c`, `nist_kw.c`, `base64.c`.
- **TLS and PSA.** `ssl_msg.c`, `ssl_tls.c`, `ssl_tls12_*.c`, `ssl_tls13_*.c`, `ssl_cookie.c`, `psa_crypto*.c`. `mbedtls_ct_hmac` (CBC MAC-then-encrypt verification) lives in `library/ssl_msg.c`.

The reach is deliberate but partial. Some functions are documented as not constant-time. `library/bignum.c:302` says leading zeros in Y may be removed and the function is not constant-time, and `bignum.c:1621` says modular exponentiation is not constant-time in the exponent. The changelog also says the RSA PKCS#1 v1.5 decryption path, even with constant-time error handling, "remains inherently dangerous" and should be avoided where possible.

**Verification, and what I could not check**

- Tests in `tests/suites/test_suite_constant_time.function` use `TEST_CF_SECRET` and `TEST_CF_PUBLIC` annotations. Under Valgrind or MSan these mark secret memory as undefined, so any secret-dependent branch or memory access shows up as an error.
- `tests/scripts/components-sanitizers.sh` runs these under MSan (`component_test_memsan_constant_flow*`) and Valgrind (`component_release_test_valgrind_constant_flow*`), with and without asm. The asm-specific run is limited to `test_suite_constant_time`.
- The test harness header `test/constant_flow.h` lives in the `framework/` submodule, which is absent from this checkout (`framework/` does not exist). I could read how the tests use the macros, but I could not confirm the macro implementations.
- The two opt-in switches, `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` and `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`, are off by default in `mbedtls_config.h`. Constant-time behaviour is therefore checked in CI only when those components run, not on every build.

In short: the mask primitives and asm are the enforcement mechanism. Plain C is the fallback, where correctness depends on compiler behaviour rather than a guarantee. Verification is test-time and opt-in. Known variable-time functions remain.