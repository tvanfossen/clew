## Short answer

Constant-time behaviour is not enforced by the compiler or by a checker. It is a coding discipline. The library builds branch-free masks with inline assembly where it can, falls back to a volatile-opaque C version elsewhere, and relies on Valgrind and MemSan test builds to catch secret-dependent branches or memory access afterwards. The facility is used in the crypto and TLS paths that handle secrets, but not uniformly, and some primitives are explicitly not constant-time.

## How it works at the instruction level

All primitives live in `library/constant_time_impl.h`, with a public memcmp in `include/mbedtls/constant_time.h` and `library/constant_time.c`.

- **Condition type.** `mbedtls_ct_condition_t` is a full-width mask: all ones for true, all zeros for false. Every operator (`mbedtls_ct_uint_lt`, `mbedtls_ct_uint_eq`, `mbedtls_ct_bool_and`, `mbedtls_ct_if`, and so on) is pure arithmetic on that mask, so there is no branch to leak on.
- **Inline asm on four targets.** When `MBEDTLS_CT_ASM` is defined, `mbedtls_ct_bool`, `mbedtls_ct_uint_lt` and `mbedtls_ct_if` use hand-written `asm volatile` sequences for AArch64, 32-bit ARM (Thumb-2 `s`-suffixed ops), x86-64, and 32-bit x86. The asm is a barrier as well as a computation: the compiler cannot see through it to rewrite it as a branch.
- **Plain-C fallback.** Everywhere else, `mbedtls_ct_compiler_opaque(x)` returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global set to 0 in `library/constant_time.c`. The compiler cannot prove that value, so it cannot specialise on the input. `mbedtls_ct_bool` then computes `-x | -(x>>1)`, takes the sign bit, and negates it to produce the mask. The code comments say this was checked against recent GCC, Clang and MSVC in May 2023 and was not turned into branches or conditional instructions.
- **Volatile memcmp.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers so the loop cannot exit early on the first difference. It reads 32 bits at a time when `MBEDTLS_EFFICIENT_UNALIGNED_VOLATILE_ACCESS` is set, then ORs the XOR differences together. It is constant-time with respect to the data but not with respect to `n`.

## What happens on a compiler that cannot support it

It does not fail the build. `MBEDTLS_CT_ASM` is gated on `MBEDTLS_HAVE_ASM` plus `__GNUC__` or `__ARMCC_VERSION`. A compiler that doesn't match, such as MSVC, or a build with assembly turned off, silently takes the C fallback. The only hard `#error` I found is in `mbedtls_ct_memcmp`, and it fires when `int` is narrower than 32 bits.

The consequence is a weaker guarantee, not a broken build. The fallback depends on the optimiser not finding the mask, and the only evidence for that is a code comment dated May 2023. The index does not show a test that checks the generated code for a particular compiler.

## How far it reaches

Callers are in the bignum core, RSA, ciphers, AEADs, PSA, TLS, and base64. The `mbedtls_ct_` helpers appear in these places:

| Area | Constant-time users (examples from the index) |
|---|---|
| Bignum | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_core_montmul`, `mbedtls_mpi_core_gcd_modinv_odd`, `mbedtls_mpi_core_cond_assign`/`cond_swap`, `mbedtls_mpi_core_ct_uint_table_lookup`, `mbedtls_mpi_lt_mpi_ct` |
| RSA | `mbedtls_rsa_rsaes_pkcs1_v15_decrypt` (unpadding), `mbedtls_rsa_rsaes_oaep_decrypt`, `mbedtls_rsa_rsassa_pkcs1_v15_verify`/`sign` (memcmp) |
| Ciphers and AEAD | PKCS padding removal in `cipher.c`, `mbedtls_cipher_check_tag`, GCM and ChaCha20-Poly1305 tag checks, CCM tag compare, CMAC multiply |
| PSA | `psa_mac_verify`, `psa_hash_verify`/`compare`, `psa_cipher_finish`, AEAD verify wrapper |
| TLS | Finished-message checks, PSK binder and identity matching, cookie check, renegotiation info, encrypted pre-master-secret parsing, `mbedtls_ssl_decrypt_buf` |
| Other | NIST KW unwrap, base64 encode/decode table lookups |

`p256-m` under `3rdparty/` is self-contained: it has its own constant-time design and a `MUL64_IS_CONSTANT_TIME` switch for platforms with a constant-time 32×32→64 multiply.

Limits the repo states itself:

- **`SECURITY.md` caveats.** It says compilers can introduce timing side channels in code meant to be constant-time. It also says the pure-software implementation uses lookup tables that are vulnerable to timing attacks. The index snippet does not show which implementation that refers to, so I would not attribute it to AES without reading the section.
- **PSA has no equivalent.** `docs/psa-transition.md` says the PSA API has no counterpart to the `mbedtls_ct_` utilities, so PSA callers reach them only through internal code.
- **Scope of verification.** See below.

## How it is verified

Verification is by test build, not by inspecting output:

- **Valgrind constant-flow** (`component_release_test_valgrind_constant_flow`). Secrets are marked with `TEST_CF_*` annotations. Valgrind's memcheck reports branches or addresses that depend on a marked secret as uninitialised-value use. The component also runs the `test_suite_constant_time` suite on the asm path.
- **MemSan constant-flow** (`component_test_memsan_constant_flow`). It builds with clang and turns off `MBEDTLS_HAVE_ASM` and AESNI, so it tests the plain-C path.
- **Coverage is limited.** `skip_suites_without_constant_flow` drops every test suite that has no `TEST_CF_` annotation. A primitive is only checked if its suite is annotated.

I could not resolve the `TEST_CF_SECRET` macro in the index, so I can't say from the index how marking is implemented. That lives in the test framework, which is outside the indexed file types.

## Gaps in this answer

- The index does not show the generated machine code. Whether a given compiler emits a branch is not something I could check.
- I read the `SECURITY.md` caveats only as search snippets, not in full.
- I didn't verify the ARM Thumb `#if` branches or the AArch64 asm operands against a real build.