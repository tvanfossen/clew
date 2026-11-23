**Short answer:** nothing in the build enforces constant time. The library writes the secret-dependent operations as branch-free bit masks, uses inline assembly on a few targets to keep the compiler from turning them back into branches, and checks the result with a Valgrind-based constant-flow test. On a compiler without that assembly it silently falls back to plain C with no error. The facility reaches the crypto and TLS paths that handle secrets. Several things I could not confirm from the index are listed at the end.

**How it is enforced at the instruction level**

- **Condition masks.** `mbedtls_ct_bool()` (`library/constant_time_impl.h:120`) turns any non-zero word into an all-ones mask (0 or ~0). The x86-64 version is `mov; neg; or; sar $63`. The AArch64 version is `neg; orr; asr #63`. The Thumb version is `negs; orrs; asrs #31`. Each is a short arithmetic sequence with no branch.
- **Selection.** `mbedtls_ct_if()` (`:205`) selects between two values with `and`/`not`/`or` on the mask, again in inline asm on the same targets.
- **Opaque values.** `mbedtls_ct_compiler_opaque()` (`:85`) puts the value through `asm volatile("" : "+r"(x))` when `MBEDTLS_CT_ASM` is defined. Otherwise it returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global (`library/constant_time.c:29`). The point is that the compiler cannot prove the value is 0 or 1, so it cannot rewrite the mask logic into a conditional jump.
- **Buffer comparison.** `mbedtls_ct_memcmp()` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers and ORs the XOR differences together, so it always touches every byte. It is constant with respect to the data, but explicitly not with respect to `n`, the length.

**What happens on an unsupported compiler**

- `MBEDTLS_CT_ASM` is defined only when `MBEDTLS_HAVE_ASM` is on and the compiler is GCC-style (`__GNUC__`) or ARMCC (`library/constant_time_impl.h:40-52`). On other compilers, such as MSVC, the code takes the `#else` branch: plain C masks, with `volatile` opacity and a `#pragma` to silence MSVC's unary-minus warning. Nothing fails to build.
- The only hard `#error` in this area is in `mbedtls_ct_memcmp`, and it fires when `int` is narrower than 32 bits. That is a sizing guard, not a constant-time check.
- The C fallback is the weaker path. The header comment says plain C "does not get optimised into conditional instructions or branches" in May 2023 for trunk clang, gcc and MSVC 19. That is a snapshot of compiler behaviour, not a guarantee. `SECURITY.md` ("Caveats") says outright that compilers can introduce timing side channels in code meant to be constant-time.

**How far it reaches**

- **Header and helpers:** `include/mbedtls/constant_time.h` (public, `mbedtls_ct_memcmp` only) and the internal `constant_time_impl.h` / `constant_time_internal.h`.
- **Modules that include it:** `bignum.c`, `bignum_core.c`, `bignum_mod.c`, `bignum_mod_raw.c`, `rsa.c`, `psa_crypto_rsa.c`, `cipher.c`, `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `nist_kw.c`, `base64.c`, `ecp_curves.c`, `pk_wrap.c`, `psa_crypto.c`, `psa_crypto_cipher.c`, `psa_crypto_mac.c`, `ssl_msg.c`, `ssl_tls.c`, `ssl_tls12_client.c`, `ssl_tls12_server.c`, `ssl_tls13_generic.c`, `ssl_tls13_server.c`, `ssl_cookie.c`.
- **Named uses:** RSA PKCS#1 v1.5 unpadding and OAEP decrypt, RSA signing and verify, CBC padding removal (`mbedtls_get_pkcs_padding`), GCM, CCM and ChaCha20-Poly1305 tag checks, PSS and MAC verify, TLS PSK binder and identity checks, TLS Finished checks, and the premaster-secret path in `ssl_parse_encrypted_pms`.
- **Bignum:** `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, conditional assign and swap, Montgomery multiplication, and table lookup.
- **Testing:** `tests/scripts/components-configuration-crypto.sh` has `test_with_valgrind_constant_time`, which runs the `constant_time` suites under Valgrind. `components-sanitizers.sh` has `component_release_test_valgrind_constant_flow`. `analyze_outcomes.py` tracks `test_suite_constant_time`.
- **Outside the facility:** `3rdparty/p256-m` does its own constant-time arithmetic. Its README gates a faster path on `MUL64_IS_CONSTANT_TIME`, which the user has to assert for their platform. The PSA `docs/psa-transition.md` notes that the PSA API has no equivalent of these utilities, so code that moves to PSA has to call them explicitly.
- **Scope limit:** `SECURITY.md` says Mbed TLS makes no guarantees against local non-timing side channels.

**What I could not confirm from the index**

- Whether the Valgrind constant-flow components run in CI on every change, and how much of each secret-handling path they exercise.
- The full list of modules that use the facility. The list above comes from `#include` search, not an exhaustive call-graph walk.
- Which compilers and optimisation levels the C fallback has actually been checked against. The index gives only the code comment's claim.