The index answers the first two parts well. For the third, it can only show the call sites it resolved, so I can't give a complete census.

## How it is enforced at the instruction level

There is no compiler-checked or build-checked guarantee. The mechanism has three layers, all in `library/constant_time_impl.h`:

1. **Branch-free masks.** `mbedtls_ct_bool(x)` turns any value into an all-zeros or all-ones mask (`MBEDTLS_CT_FALSE` / `MBEDTLS_CT_TRUE`). The comparisons (`mbedtls_ct_uint_eq/lt/ne/...`) and selectors (`mbedtls_ct_if`, `mbedtls_ct_uint_if`, `mbedtls_ct_size_if`) are built from these masks with AND/OR/NOT, so secret values never reach a branch.
2. **Hand-written asm where available.** `mbedtls_ct_bool` and `mbedtls_ct_if` have inline asm variants for AArch64, 32-bit Thumb ARM, x86-64 and 32-bit x86. For example, the x86-64 `mbedtls_ct_bool` is `mov / neg / or / sar`, and the ARM variant is `negs / orrs / asrs`. The asm pins the instruction sequence, so the compiler cannot turn it back into a branch.
3. **The optimisation barrier.** `mbedtls_ct_compiler_opaque(x)` hides a value from the optimiser. With asm it is an empty `asm volatile("" : "+r"(x))`. Without asm it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global that is 0. The point is that the compiler cannot prove the mask's value and fold the code into a branch or a `cmov`.

`mbedtls_ct_memcmp` (`library/constant_time.c`) uses a different technique. It reads both buffers through `volatile` pointers so every byte is always read, ORs the XORs into an accumulator, and folds the result into an `int`. It is constant with respect to the data but not to `n`. The index marks it `orphan` (no in-library caller found), which may be an index gap since it is public API in `include/mbedtls/constant_time.h`.

## What happens on a compiler that cannot support it

The asm path is gated by `MBEDTLS_CT_ASM`, which is defined only when `MBEDTLS_HAVE_ASM` is set and the compiler is GCC-compatible or ARMCC. The arch-specific macros (`MBEDTLS_CT_X86_64_ASM`, `MBEDTLS_CT_ARM_ASM`, and so on) further check `__x86_64__`/`__amd64__`, `__arm__` with Thumb, and similar. I did not check the AArch64 gate.

On any other compiler there is no build error and no `#error`. The code silently falls back to plain C. The masks come from the sign-bit trick (`(-xo) | -(xo >> 1)`), and the barrier from the volatile-zero XOR. The header comment says this fallback "does not get optimised into conditional instructions or branches by trunk clang, gcc, or MSVC v19 (May 2023)". That is a dated observation, not a guarantee.

Two smaller degradations:
- `MBEDTLS_CT_SIZE_64` is only chosen when `MBEDTLS_HAVE_INT64` is available. Otherwise the 32-bit variants are used.
- `mbedtls_ct_memcmp` contains an `#error` only for `INT_MAX < INT32_MAX`, which is the one guard I saw in that file.

`SECURITY.md` says the project uses standard C "except with known compilers", and that "compilers can introduce timing side channels in code that was intended to be constant-time." So the library's own documentation treats this as best effort.

## How far it reaches

The primitives are used in these places, as resolved by the index:

| Area | Call site | Notes |
|---|---|---|
| TLS record MAC | `mbedtls_ct_hmac` in `library/ssl_msg.c` | Uses `psa_hash_clone` to finish the hash over every candidate length. Gated by `MBEDTLS_SSL_SOME_SUITES_USE_MAC` and `MBEDTLS_USE_PSA_CRYPTO`. |
| RSA PKCS#1 v1.5 decrypt | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` in `library/rsa.c` | Written against Bleichenbacher-style padding oracles. Called from `mbedtls_rsa_rsaes_pkcs1_v15_decrypt`. |
| CBC padding | `mbedtls_get_pkcs_padding` in `library/cipher.c` | Reads a fixed `input_len` bytes regardless of padding length. Gated by `MBEDTLS_CIPHER_PADDING_PKCS7`. |
| Base64 | `mbedtls_ct_base64_dec_value` / `enc_char` in `library/base64.c` | |
| Bignum | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_lt_mpi_ct`, `mbedtls_mpi_gcd_modinv_odd`, plus `mbedtls_ct_mpi_uint_if` and `mbedtls_ct_mpi_sign_if` in `bignum.c` | |
| Secret-indexed copies | `mbedtls_ct_memcpy_if`, `mbedtls_ct_memcpy_offset`, `mbedtls_ct_memmove_left`, `mbedtls_ct_zeroize_if` in `library/constant_time.c` | Used by the TLS and RSA code above. |

Testing is limited. `test_with_valgrind_constant_time` in `tests/scripts/components-configuration-crypto.sh` runs `tests/suites/*constant_time*.data` under Valgrind, but it excludes `test_suite_constant_time_hmac.data` through `GLOBIGNORE`. The index does not say why that suite is excluded.

Outside the facility:
- `3rdparty/p256-m` has its own constant-time approach, with `CT_VALGRIND`, `CT_MEMSAN` and `MUL64_IS_CONSTANT_TIME` macros. These are not part of `constant_time.h`.
- The PSA docs say the PSA API has no equivalent to these utilities. The `psa_aead_verify` documentation asks implementations to "make the best effort" to compare tags in constant time.

## Gaps

- The index cannot show whether a given secret-dependent branch elsewhere in the library was converted. Many callers of each primitive are unresolved (`mbedtls_ct_uint_eq` reports 12 unresolved call sites), so this census is incomplete.
- Nothing here checks the generated machine code. The guarantee rests on the asm variants and the barrier idiom, and on the Valgrind tests, not on a disassembly check.
- I did not read the full `SECURITY.md` caveat section. The snippets above are from search hits.