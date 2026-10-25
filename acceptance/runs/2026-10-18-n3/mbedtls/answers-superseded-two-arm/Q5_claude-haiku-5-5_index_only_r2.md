## Short answer

Constant-time code in mbedtls is a small set of `mbedtls_ct_*` primitives. They compute with masks instead of branches. On a few architectures, inline asm pins the instruction sequence. Everywhere else, plain C is used and the compiler is trusted not to reintroduce branches. Nothing fails the build when asm is unavailable; the fallback is silent. The primitives are used in the bignum core, RSA PKCS#1 v1.5 unpadding, the TLS HMAC path, and base64. The index cannot give a complete census of callers, so I can't confirm coverage beyond those.

## 1. How it is enforced at the instruction level

The primitives are `static inline` in `library/constant_time_impl.h`. Their conventions:

- **Conditions are masks.** `mbedtls_ct_condition_t` is all-ones or all-zeros. `mbedtls_ct_bool(x)` turns any word into a mask: nonzero gives all ones.
- **Opacity barrier.** `mbedtls_ct_compiler_opaque(x)` stops the optimizer from proving anything about a value. With asm it is `asm volatile("" : [x] "+r"(x))`. Without asm it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global set to 0.
- **Asm bodies.** On x86_64, `mbedtls_ct_bool` is `mov; neg; or; sar $63`, which produces the mask with no jump and no flag-dependent branch. `mbedtls_ct_if` is `and; not; and; or`, a bitwise select. `mbedtls_ct_uint_lt` is a fixed subtract-and-borrow sequence in asm, with a fallback that works on the sign bit of `x - y`.
- **Byte comparison.** `mbedtls_ct_memcmp` (`library/constant_time.c`) reads both buffers through `volatile` pointers, XORs into an accumulator, and never exits early. Its doc says it is not constant with respect to `n`.
- **Limits.** The asm fixes the instruction sequence. Whether those instructions take data-independent time is a property of the CPU, which the index does not cover.

## 2. What happens on a compiler or architecture without support

Selection is by preprocessor gates:

| Condition | Result |
|---|---|
| `MBEDTLS_HAVE_ASM` set, and `__GNUC__` or `__ARMCC_VERSION` | `MBEDTLS_CT_ASM` defined |
| …and arch is AArch64, Thumb ARM, x86_64, or x86 | Arch-specific asm for `ct_bool`, `ct_if`, `ct_uint_lt` |
| Asm arch-specific choice is also size-gated | `MBEDTLS_CT_SIZE_32` / `_64`, from `MBEDTLS_HAVE_INT64` |
| Anything else (MSVC, other arches, asm disabled in config) | Plain C fallback |

Things to note about the fallback:

- **Silent.** There is no `#error` and no warning. The only `#error` on this path is in `mbedtls_ct_memcmp`, and it fires only for `int` narrower than 32 bits.
- **Dated claim.** The header says the C fallback, as of May 2023, is not turned into branches by trunk gcc, clang, or MSVC 19. That is an observation about specific compiler versions, not a guarantee.
- **Repository admission.** `SECURITY.md` says compilers can introduce timing side channels in code meant to be constant-time, and that Mbed TLS provides only limited protection against timing attacks.
- **Config coupling.** `MBEDTLS_HAVE_ASM` is a user config switch. Disabling asm for debugging also silently changes the constant-time codegen.

## 3. How the property is checked

- `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25`) runs `tests/suites/*constant_time*.data` under Valgrind. It excludes the HMAC suite through `GLOBIGNORE`. The index does not say why HMAC is excluded.
- `docs/architecture/psa-shared-memory.md` says Valgrind memory poisoning is already used for constant-flow testing.
- I found no static constant-time check in the index. `CT_VALGRIND` and `CT_MEMSAN` appear only in `3rdparty/p256-m`, not in the `mbedtls_ct` module. The index does not show what those macros actually do in the test build.

## 4. How far it reaches

Confirmed users, from dossiers and name search:

| Area | Symbols | Notes |
|---|---|---|
| Bignum core | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_lt_mpi_ct` (public), `mbedtls_mpi_gcd_modinv_odd`, `mbedtls_ct_mpi_uint_if` | `lt_ct` loops over every limb with no early exit |
| RSA | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` | Comment explicitly targets Bleichenbacher-style oracles via timing, memory access, and branches |
| TLS record | `mbedtls_ct_hmac` (`library/ssl_msg.c`) | Clones the hash context and finishes it for every candidate length, so work does not depend on the secret length. Gated on `MBEDTLS_SSL_SOME_SUITES_USE_MAC` and `MBEDTLS_USE_PSA_CRYPTO` |
| Padding | `mbedtls_get_pkcs_padding` calls `mbedtls_ct_if` | Via the index's callers list |
| Base64 | `mbedtls_ct_base64_dec_value`, `mbedtls_ct_base64_enc_char` | Table-free range masks |
| Helpers | `mbedtls_ct_memcpy_offset`, `mbedtls_ct_memcmp_partial`, `mbedtls_ct_zeroize_if`, `mbedtls_ct_memmove_left` | `memcpy_offset` reads every candidate offset |

Gaps and limits:

- **`mbedtls_ct_memcmp` is marked orphan** by the index, so I could not trace its callers. The PSA docs recommend it for MAC comparison, but the index does not confirm the PSA core calls it.
- **Caller counts are unresolved.** Several primitives report 6 to 26 unresolved callers. I cannot say from the index whether ECC scalar multiplication, AES, or modular exponentiation use these primitives.
- **PSA has no equivalent.** `docs/psa-transition.md` says the PSA API has no counterpart to the timing utilities. PSA AEAD verify only promises a best-effort constant-time tag comparison.
- **`3rdparty/p256-m` is separate.** Its README says it is constant-time from the ground up with its own macros. It does not use the `mbedtls_ct` module.

To answer the coverage question for a specific algorithm, I'd need to check its callers against the `mbedtls_ct_*` list. Dossier on that algorithm's functions would show whether they call any of these primitives.