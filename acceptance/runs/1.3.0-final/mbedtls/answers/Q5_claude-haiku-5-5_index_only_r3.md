The index answers this from source, not from compiled output, so nothing below shows what the compiler actually emitted. Read the source as the design, not as proof of the binary.

## How it's enforced at the instruction level

The primitives live in `library/constant_time_impl.h`, with the public API in `include/mbedtls/constant_time.h` and helpers in `library/constant_time.c`. Two mechanisms do the work:

1. **Hand-written assembly for each primitive.** Each function (`mbedtls_ct_bool`, `mbedtls_ct_if`, `mbedtls_ct_uint_lt`) has per-architecture `asm volatile` branches for AArch64, ARM (32-bit, Thumb-aware), x86-64 and x86-32. For example, `mbedtls_ct_bool` on x86-64 is `mov; neg; or; sar $63`, which turns any nonzero input into an all-ones mask with no branch or conditional instruction. `mbedtls_ct_if` is a mask select (`and/not/and/or`).

2. **An opacity barrier for the C fallback.** `mbedtls_ct_compiler_opaque(x)` returns `x` through `asm volatile("" : "+r"(x))` when assembly is available. Otherwise it returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global. The stated purpose is that the compiler cannot prove the value at compile time, so it cannot fold the mask back into a branch.

Constant-time checks are then built from these. `mbedtls_ct_uint_lt` and similar compute the comparison with bit arithmetic on the MSB, and `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers so it cannot exit early. Callers combine results with `mbedtls_ct_bool_and/or/not` and select with `mbedtls_ct_if`, so secrets never reach an `if`.

## What happens on a compiler that can't support it

The assembly path is gated by `MBEDTLS_CT_ASM`, which is defined only when `MBEDTLS_HAVE_ASM` is set and the compiler is GCC-compatible (`__GNUC__`) or ARM Compiler (`__ARMCC_VERSION`). `MBEDTLS_HAVE_ASM` is on by default (`include/mbedtls/mbedtls_config.h:52`). The per-architecture macros (`MBEDTLS_CT_X86_64_ASM` etc.) are then chosen by target.

On any other compiler or target, every primitive falls to its plain C `#else` branch. That branch uses the opacity barrier and bit operations, and its comment says it "does not get optimised into conditional instructions or branches by trunk clang, gcc, or MSVC v19" as of May 2023. The index found no `#error` or build failure for the fallback. The only `#error` in this area is for ints narrower than 32 bits in `mbedtls_ct_memcmp`. So an unsupported compiler **silently gets the C fallback**, and the guarantee drops from "verified assembly" to "hopefully not optimised". `SECURITY.md` says the same thing in its Caveats section: compilers "can introduce timing side channels in code that was intended to be constant-time."

## How far it reaches

The facility is opt-in per call site. Callers I could identify:

| Area | Constant-time users (examples) |
|---|---|
| Bignum | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_core_montmul`, `mbedtls_mpi_gcd_modinv_odd`, `mbedtls_mpi_safe_cond_assign/swap`, `mbedtls_mpi_lt_mpi_ct`, `mbedtls_mpi_mod_raw_cond_assign/swap` |
| RSA | `mbedtls_rsa_rsaes_oaep_decrypt`, `mbedtls_ct_rsaes_pkcs1_v15_unpadding`, PKCS#1 v1.5 sign and verify |
| AEAD / MAC tags | `mbedtls_gcm_auth_decrypt`, `mbedtls_ccm_compare_tags`, `mbedtls_chachapoly_auth_decrypt`, `mbedtls_cipher_check_tag`, `mbedtls_nist_kw_unwrap`, `psa_mac_verify`, `psa_hash_verify/compare` |
| Padding | `mbedtls_get_pkcs_padding` (`cipher.c`), `cmac_multiply_by_u` |
| TLS | `mbedtls_ct_hmac` and `mbedtls_ssl_decrypt_buf` (`ssl_msg.c`), `mbedtls_ssl_parse_finished`, TLS 1.2 encrypted-PMS parsing, TLS 1.3 PSK binder and identity checks, cookie check |
| Other | `mbedtls_ct_base64_enc_char` / `dec_value` (`base64.c`), `mbedtls_ct_memcpy_if`, `mbedtls_ct_zeroize_if` |

The public `mbedtls_ct_memcmp` is documented as constant-time with respect to the data but **not** with respect to `n`, so buffer lengths can leak.

Coverage gaps and limits:
- **Not everything is covered.** `SECURITY.md` says the pure-software AES implementation uses lookup tables, which are vulnerable to timing attacks. The index does not show a constant-time replacement for that path.
- **Local non-timing side channels are out of scope.** `SECURITY.md` says Mbed TLS makes no guarantees against them.
- **Verification is by Valgrind, not by inspection.** `test_with_valgrind_constant_time` runs `tests/suites/*constant_time*.data` under Valgrind. It excludes the HMAC constant-time suite via `GLOBIGNORE`, and the index does not say why.

I could not confirm the full text of the `SECURITY.md` Caveats section, the Valgrind test mechanism itself, or the real fallback behaviour on specific compilers. These are only snippets. To settle the instruction-level question, disassemble a GCC x86-64 build and check that the branch-free sequences survive, and build once with `MBEDTLS_HAVE_ASM` off to see what the C fallback produces.