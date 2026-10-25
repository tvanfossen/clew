## Short answer

Constant-time behaviour in mbedtls is a best-effort discipline, not a compiler-enforced guarantee. A small internal layer builds branch-free bitmask primitives. Inline assembly pins the critical ones on a few architectures, and a volatile barrier stops the compiler from folding the masks back into branches. Above that layer, a handful of bignum, RSA, ECP, TLS-MAC and base64 routines are written in that style. Nothing at build time rejects a compiler that can't preserve it.

## How it is enforced, bottom up

```
  consumers     rsa.c unpadding · ssl_msg.c ct_hmac · bignum_core.c lt_ct · ecp.c select_comb · base64.c
       │
  public API    include/mbedtls/constant_time.h   mbedtls_ct_memcmp, memcpy_if, memcpy_offset, ...
       │
  primitives    library/constant_time_impl.h      mbedtls_ct_bool / uint_eq / uint_lt / if / error_if ...
       │         (inline; per-arch asm or plain C)
  barrier       mbedtls_ct_compiler_opaque(x)     asm volatile("" : "+r"(x))   or   x ^ mbedtls_ct_zero
```

1. **Masks, not branches.** A condition is all-ones or all-zeros (`mbedtls_ct_condition_t`). Selection is bitwise: `(cond & a) | (~cond & b)`. `mbedtls_ct_bool` turns a value into a mask with negate/or/shift.
2. **Compiler barrier.** `mbedtls_ct_compiler_opaque` hides the value from the optimizer. With `MBEDTLS_CT_ASM` it is an empty `asm volatile` that passes the value through a register. Without it, it XORs with `mbedtls_ct_zero`, a `volatile` global holding 0, so the compiler cannot prove the value.
3. **Hand-written asm, per architecture.** `mbedtls_ct_bool` and `mbedtls_ct_if` have asm for AArch64, ARM Thumb (32-bit), x86-64 and x86-32. `MBEDTLS_CT_ASM` is only defined when `MBEDTLS_HAVE_ASM` is set and the compiler is GCC-like or ARMCC. Some asm paths require `MBEDTLS_CT_SIZE_32` or `SIZE_64` to match the word size.
4. **Volatile reads for comparison.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers, so every byte is always read. It ORs the XOR differences together, then folds the result so it is non-zero iff the buffers differ. Its doc says it is not constant with respect to `n`, which is public.

## What happens on a compiler that can't support it

- **No `#error`, no fallback warning.** When the asm guards are false, the plain-C paths run. The `volatile` zero and the mask arithmetic remain, but nothing checks that the optimizer kept them branch-free.
- **The only compile-time guard I found** is in `mbedtls_ct_memcmp`: it refuses to build if `int` is narrower than 32 bits, because a narrow cast could drop the difference bits.
- **Documented stance.** The `mbedtls_ct_bool` comment says the C fallback was checked in May 2023 and was not turned into branches by trunk clang, GCC or MSVC v19. That is a dated observation, not a guarantee. `SECURITY.md` ("Caveats") says compilers can introduce timing side channels in code meant to be constant-time, and that the project treats exploitable ones as vulnerabilities "if they appear with a common compiler". So an unusual toolchain gets the plain-C path with no guarantee, and the project's remedy is a bug report.

## How it is verified

- `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh`) runs the `tests/suites/*constant_time*.data` suites under Valgrind. It excludes the HMAC constant-time suite via `GLOBIGNORE`; the index does not record why.
- The repo's own docs describe a testing approach using Valgrind memory poisoning for control-flow checks. That is the only verification I found in the index.

## How far it reaches

| Area | Constant-time entry points | Purpose (from index) |
|---|---|---|
| Generic helpers | `mbedtls_ct_memcmp`, `memcpy_if`, `memcpy_offset`, `memmove_left`, `zeroize_if`, `memcmp_partial` | Buffer compare, conditional copy, copy from secret offset |
| Bignum | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_lt_mpi_ct`, `mbedtls_mpi_gcd_modinv_odd`, `mbedtls_ct_mpi_sign_if` | Secret-scalar comparisons, modular inverse |
| RSA | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` (called from `mbedtls_rsa_rsaes_pkcs1_v15_decrypt`) | Bleichenbacher padding-oracle resistance |
| ECP | `ecp_select_comb` | Table selection without secret-indexed access |
| TLS record MAC | `mbedtls_ct_hmac` (`ssl_msg.c`) | CBC MAC verification with constant flow; uses `psa_hash_clone` |
| Padding / encoding | `mbedtls_get_pkcs_padding`, `mbedtls_ct_base64_dec_value` / `enc_char` | Branch-free padding check and base64 |
| Third-party | p256-m (`3rdparty/p256-m`) | Its own constant-time design (Fermat inversion); has a `MUL64_IS_CONSTANT_TIME` switch |

The facility stops at the library's boundary in two ways:

- **Not every secret path uses it.** Most of the library, including plenty of code that handles secrets, does not call `mbedtls_ct_*`. Only the places listed above were found.
- **PSA is outside it.** `docs/psa-transition.md` says the PSA API has no equivalent of these utilities. The PSA spec for AEAD verify says only that implementations "shall make the best effort" to compare tags in constant time.

## What I could not settle from the index

- I did not read the full bodies of `mbedtls_ct_hmac` or `mbedtls_ct_rsaes_pkcs1_v15_unpadding`; the index truncated them. I only know their documented intent.
- I did not confirm which callers are compiled in each configuration, or whether any constant-time path is switched off under a config option.
- The rest of the `SECURITY.md` caveat sentence was truncated in the index, so I cannot quote its exact wording beyond the part above.
- The index has no build-system or CI definitions, so I could not confirm which compilers the CI actually covers.