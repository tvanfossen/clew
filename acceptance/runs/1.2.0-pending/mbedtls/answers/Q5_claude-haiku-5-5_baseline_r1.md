**Short answer:** mbedtls enforces constant time by convention and by a small primitive layer, not by any compiler or build-time check. The primitives are assembly on a few architectures and portable C everywhere else. A test harness then looks for secret-dependent branches under Valgrind or MSan. The library's own SECURITY.md says the protection is limited and that compiler-introduced timing leaks may not be fully prevented.

**How it works at the instruction level**

- The API is `library/constant_time_impl.h` and `library/constant_time_internal.h`, with `include/mbedtls/constant_time.h` as the public header. Secrets are held as `mbedtls_ct_condition_t` masks that are all-ones or all-zeros. Callers combine them with `mbedtls_ct_bool*`, `mbedtls_ct_uint_*`, `mbedtls_ct_*_if`, `mbedtls_ct_memcpy_if` and `mbedtls_ct_memcmp`. None of these branch on the secret.
- On GCC/Clang-compatible compilers with `MBEDTLS_HAVE_ASM` set, the core operations are hand-written `asm volatile` for AArch64, 32-bit Arm/Thumb, x86-64 and x86. For example, the x86-64 `mbedtls_ct_bool` is `neg`/`or`/`sar $63`, and `mbedtls_ct_if` is `and`/`not`/`and`/`or`.
- `mbedtls_ct_compiler_opaque()` stops the optimiser from learning a value. With asm it is an empty `asm volatile("" : "+r"(x))` barrier. Without asm it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global set to 0 that the compiler cannot fold.
- `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers, so it cannot exit early. It accumulates the XOR difference and returns the result without a data-dependent branch.

**What happens on a compiler that cannot support it**

There are three tiers:

| Situation | Result |
|---|---|
| `MBEDTLS_HAVE_ASM` undefined, or the compiler is not GNU-style (MSVC, IAR, old armcc) | `MBEDTLS_CT_ASM` is not defined. The portable C fallback is used, with `mbedtls_ct_zero` as the barrier. |
| GNU-style compiler on an architecture with no specific branch (e.g. RISC-V) | `MBEDTLS_CT_ASM` is defined, so only the generic empty-asm barrier is used. Every operation falls through to its C `#else` branch. |
| Supported arch, but the word size does not match the asm variant (e.g. the 32-bit x86 asm on a 64-bit `mbedtls_ct_uint_t`) | Falls through to C for that operation. |

The C fallback is only "designed to yield constant-time code". `constant_time_internal.h` says it was observed to be constant time on recent gcc, clang and MSVC as of May 2023. Nothing fails to build, and nothing warns that the code has lost its guarantee. The one hard error is `mbedtls_ct_memcmp` on platforms with `int` narrower than 32 bits.

**How it is verified**

- `tests/suites/test_suite_constant_time*.function` tests each primitive for values. It uses `TEST_CF_SECRET`/`TEST_CF_PUBLIC` from `framework/tests/include/test/constant_flow.h` to mark memory as secret or public.
- `tests/scripts/components-configuration-crypto.sh` runs `test_with_valgrind_constant_time` over `*constant_time*.data`. This is Valgrind memcheck, which reports any branch or address that depends on undefined (secret) data.
- `tests/scripts/components-sanitizers.sh` runs the constant-time suite under Valgrind/MSan, and has a separate step for the asm path.
- The `framework/` submodule is empty in this checkout, so `constant_flow.h` is missing and I could not confirm how the macros are implemented or run these suites here. The description above comes from the test sources and the scripts.

**How far it reaches**

Constant-time code is used in these places:
- **RSA** (`rsa.c`, about 37 uses): PKCS#1 v1.5 padding checks and unpadding.
- **Bignum** (`bignum_core.c`, `bignum.c`, `bignum_mod_raw.c`): `*_ct` routines, conditional swap and assign, zero checks, and comparisons.
- **TLS record layer** (`ssl_msg.c`): CBC padding checks, and HMAC and MAC verification via `mbedtls_ct_hmac` and `mbedtls_ct_memcmp`. Also `ssl_tls12_server.c`, `ssl_cookie.c` and parts of TLS 1.3.
- **Cipher and AEAD tag checks** (`cipher.c`, `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `nist_kw.c`), and `base64.c`.
- **PSA** (`psa_crypto*.c`): MAC comparison and some RSA/cipher paths.
- **ECC** (`ecp.c`): the comb-method fixed-base multiplication uses `ecp_select_comb` and a scalar recoding step explicitly labelled "constant-time". Variable-base shortcuts, `mbedtls_ecp_muladd` and the restartable variant are explicitly marked "NOT constant-time".

Things that are not constant time:
- **AES, Camellia, ARIA and DES** software implementations use lookup tables. SECURITY.md says this leaks; the workarounds are hardware acceleration, an alternative implementation, or switching to ChaCha20/Poly1305 and HMAC_DRBG.
- **ECC** depends on the implementation chosen. X25519 via Everest protects against remote timing only. p256-m is included under `3rdparty/`.
- **Anything outside the threat model** in SECURITY.md: local non-timing channels, fault injection, and physical attacks.

**Caveats**

- The guarantee is only as good as the compiler's behaviour on the code it actually emits. SECURITY.md recommends `-O2` or `-Os`, and says `-O3` and `-Oz` are less scrutinised.
- Constant-time code only matters if the surrounding code is also constant time. The library states it is "moving towards" fully timing-invariant code but has not reached it.
- Tool output from one of my Bash calls carried an extra instruction about a `dossier` tool. I ignored it; it had nothing to do with your question.