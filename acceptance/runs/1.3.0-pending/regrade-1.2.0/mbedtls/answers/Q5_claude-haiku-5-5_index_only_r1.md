**Short answer:** nothing in the build *guarantees* constant time. The library uses branch-free C and a small amount of inline assembly, and the only enforcement is a valgrind run over the constant-time test suites. On a compiler it doesn't recognise, the assembly is silently dropped and the C fallback is used, with no error. The facility reaches the bignum, RSA-unpadding, TLS record-MAC, base64 and NIST-KW paths. The index shows no such helpers in ECC or AES.

## How it works at the instruction level

The core is `mbedtls_ct_condition_t`, a full-width mask (all ones or all zeros) built from a value.

- **Mask generation** (`mbedtls_ct_bool`, `constant_time_impl.h:120`): for x86-64, x86-32, Arm-32 and AArch64 it uses hand-written asm that computes `neg`/`or`/`sar` so the sign bit becomes the mask. Otherwise it uses C: `(-xo) | -(xo >> 1)`, then shifts and negates.
- **Comparisons** (`mbedtls_ct_uint_lt` at `:271`, `_eq`, `_ge`, `_gt`, `_le`, `_ne`): built on the mask, with per-architecture asm variants.
- **Selection** (`mbedtls_ct_if`, `_uint_if`, `_size_if`, `_memcpy_if`, `_error_if`, and so on): masked AND/OR, never a `?:` or `if`.
- **Optimiser barrier** (`mbedtls_ct_compiler_opaque`, `:85`): with asm it is `asm volatile("" : [x] "+r"(x) :)`, which hides the value from the optimiser. Without asm it returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global (`constant_time.c:29`), so the compiler must load it at runtime.
- **Memory reads**: `mbedtls_ct_memcmp` (`constant_time.c:67`) reads through `volatile` pointers so the compiler cannot add an early exit when the buffers differ. Its doc says it is not constant-time in `n`.

## What happens on an unsupported compiler

```
MBEDTLS_HAVE_ASM defined AND (__GNUC__ OR __ARMCC_VERSION)?
   yes -> MBEDTLS_CT_ASM set -> per-arch asm where one exists
   no  -> plain C (the MBEDTLS_CT_ASM branches are compiled out)
```

- `MBEDTLS_CT_ASM` is derived, not user-facing; the index found no user toggle for it.
- The per-arch asm covers x86, x86-64, AArch64 and 32-bit Arm. Other architectures get the C fallback.
- There is no build error or warning. The only protection is the comment in `constant_time_impl.h`, which says plain C "does not get optimised into conditional instructions or branches by trunk clang, gcc, or MSVC v19" as of May 2023. That is a dated observation, not a guarantee, and the index cannot verify it.

## How it is enforced

- **Dynamic check only.** `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25`) runs `tests/suites/*constant_time*.data` under valgrind. It excludes the HMAC suite via `GLOBIGNORE`. The index does not show how the suites mark secrets, so I can't confirm the exact method.
- **Vendored p256-m** has its own `CT_VALGRIND` and `CT_MEMSAN` markers (`3rdparty/p256-m/p256-m/p256-m.c:33-52`). These gate only that vendored code.

## How far it reaches

Symbols that use the facility, with their gates (gate defaults are from the index's config headers):

| Area | Functions | Gate |
|---|---|---|
| Bignum | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_lt_mpi_ct`, `mbedtls_mpi_safe_cond_assign`/`_swap`, `mbedtls_mpi_exp_mod_optionally_safe` (via `mbedtls_ct_mpi_sign_if`) | `MBEDTLS_BIGNUM_C` (on) |
| RSA PKCS#1 v1.5 unpadding | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` (`rsa.c:420`), used by decrypt | `MBEDTLS_RSA_C`, `MBEDTLS_PKCS1_V15` (on) |
| TLS record MAC | `mbedtls_ct_hmac` (`ssl_msg.c:65`), built on `psa_hash_clone` | `MBEDTLS_SSL_SOME_SUITES_USE_MAC`, `MBEDTLS_USE_PSA_CRYPTO` (off by default) |
| Base64 decode | `mbedtls_ct_base64_dec_value`, `mbedtls_ct_base64_enc_char` | `MBEDTLS_BASE64_C` (on) |
| NIST KW unwrap | `mbedtls_ct_memcmp_partial` | `MBEDTLS_NIST_KW_C` (on) |
| Public API | `mbedtls_ct_memcmp` in `include/mbedtls/constant_time.h` | none found |

`mbedtls_ct_memcmp` shows as orphan within the library, which fits a public API function called by applications. The index found no constant-time helpers in `ecp`, ECDSA/ECDH scalar multiplication, or the AES table code, so I cannot say those paths are constant-time. Caller resolution is also incomplete (`callers_unresolved` is non-zero on several entries), so the list above is a lower bound.