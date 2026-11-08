**Short answer:** Mbed TLS does not verify constant-time behaviour at the instruction level. It makes the compiler's job harder and then trusts the result. Enforcement is by convention plus inline assembly on a few targets, with a plain-C fallback everywhere else. The facility reaches the secret-dependent code paths in RSA, TLS record and handshake processing, AEAD/CMAC tag checks, PSA verify operations and the bignum core. I could not confirm from the index that every such path uses it.

**How it is enforced**

- **Public surface is tiny.** `include/mbedtls/constant_time.h` exports only `mbedtls_ct_memcmp()`. Its body (`library/constant_time.c:67`) reads both buffers through `volatile` pointers so the compiler cannot exit early on the first mismatch, and accumulates `diff |= x ^ y`. It is documented as "not constant-time w.r.t. n", so the length must be public.
- **Internal toolkit.** `library/constant_time_impl.h` builds branch-free primitives on top of `mbedtls_ct_condition_t` masks: `mbedtls_ct_bool`, `_uint_eq/ne/lt/le/gt/ge`, `_if`, `_if_else_0`, `_bool_and/or/not`, `_error_if`, and `mbedtls_ct_uchar_in_range_if`. `library/constant_time_internal.h` holds the typedefs and size macros, and `library/constant_time.c` holds the memory helpers (`mbedtls_ct_memcpy_if`, `_memcpy_offset`, `_memmove_left`, `_zeroize_if`).
- **Hiding values from the optimiser.** `mbedtls_ct_compiler_opaque(x)` is the key helper. With inline asm (`asm volatile("" : [x] "+r"(x))`) it pins the value in a register. Without asm it returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a global `volatile` zero, so the compiler cannot prove the value.
- **Mask generation.** `mbedtls_ct_bool(x)` turns "x != 0" into an all-ones or all-zeros mask. On AArch64, 32-bit ARM and x86/x86-64 it uses hand-written `asm volatile` sequences (`neg`/`orr`/`asr`, or `mov`/`neg`/`or`/`sar`) selected by `MBEDTLS_CT_AARCH64_ASM`, `MBEDTLS_CT_ARM_ASM`, `MBEDTLS_CT_X86_64_ASM` and `MBEDTLS_CT_X86_ASM`, combined with a word-size macro (`MBEDTLS_CT_SIZE_32`/`_64`).
- **Gate for asm.** `MBEDTLS_CT_ASM` is only defined under `MBEDTLS_HAVE_ASM` with a GNU-style or ARM compiler (`library/constant_time_impl.h:40-52`). The `MBEDTLS_HAVE_ASM` gate is set in `include/mbedtls/mbedtls_config.h:52` and in several config profiles.
- **Guard against silent truncation.** `mbedtls_ct_memcmp` has a `#error` if `int` is narrower than 32 bits, because it casts a `uint32_t` mask to `int` and must not lose the high bits.

**What happens on a compiler that cannot support it**

There is no build error for an unsupported compiler. The code silently falls back in two places:

1. If `MBEDTLS_CT_ASM` is not defined, `mbedtls_ct_compiler_opaque` uses the `volatile`-zero XOR trick.
2. The asm `mbedtls_ct_bool` variants are used only for the listed architecture and word-size combinations. Anything else uses the arithmetic C version (`y = (-xo) | -(xo >> 1)`, then sign-bit extraction).

The header comment says the C fallback "does not get optimised into conditional instructions or branches by trunk clang, gcc, or MSVC v19" as of May 2023. That is an observed property of particular compiler versions, not a guarantee. `SECURITY.md` says so directly: "compilers can introduce timing side channels in code that was intended to be constant-time", and the project treats exploitable ones "as a vulnerability if they appear with a common compiler". The project therefore relies on testing with specific compilers (the README lists GCC, Clang, Arm Compiler 6, IAR and MSVC) plus its own tests, not on any static proof. `p256-m`'s README is more explicit about platform dependence: it has a `MUL64_IS_CONSTANT_TIME` switch for cores whose 32×32→64 multiply is constant-time.

**How far it reaches**

Callers of the primitives, all found in the index:

| Area | Examples |
|---|---|
| RSA | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` (`library/rsa.c:420`), OAEP decrypt, PKCS#1 v1.5 sign/verify, decrypt decomposition |
| TLS record layer | `mbedtls_ct_hmac` (`library/ssl_msg.c:65`) for constant-flow MAC over padded records, and `mbedtls_ssl_decrypt_buf` |
| TLS handshake | TLS 1.2 server encrypted-PMS and PSK identity parsing, TLS 1.3 server binder and identity matching, `mbedtls_ssl_parse_finished`, cookie check |
| Symmetric tags | `mbedtls_gcm_auth_decrypt`, `mbedtls_chachapoly_auth_decrypt`, `mbedtls_ccm_compare_tags`, `mbedtls_nist_kw_unwrap`, `mbedtls_cipher_check_tag`, CBC padding removal in `library/cipher.c` |
| PSA | MAC verify, hash compare/verify, AEAD verify, cipher finish/decrypt, RSA asymmetric decrypt |
| Bignum | `mbedtls_mpi_core_montmul`, `mbedtls_mpi_core_gcd_modinv_odd`, `mbedtls_mpi_core_ct_uint_table_lookup`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_safe_cond_assign/swap`, `mbedtls_mpi_mod_raw_cond_assign/swap`, `mbedtls_mpi_lt_mpi_ct` |

The ECP and ECDH code is not confirmed here. My queries surfaced `ecp_modp` and comb-recode code in `library/ecp.c`, but no `mbedtls_ct_*` callers there, so I cannot say whether scalar multiplication is covered by this facility.

**Limits of the index**

- It cannot show the generated machine code, so claims about actual branch-free output rest on the source comments and the project's testing, not on anything I could read.
- Local non-timing side channels are explicitly out of scope: `SECURITY.md` says Mbed TLS "doesn't make any security guarantees against local non-timing-based side channel attacks".
- Some code is not reachable through this index's coverage. Absence of a call site here is not proof of an unprotected path.