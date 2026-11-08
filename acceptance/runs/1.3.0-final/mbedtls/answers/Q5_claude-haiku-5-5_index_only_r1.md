**Short answer:** constant-time behaviour is not enforced by the compiler or by any check I can see in the index. It comes from a small set of branch-free primitives in `library/constant_time_impl.h`, which use inline assembly where the target allows and plain C otherwise. Whether the output is actually constant-time is left to a Valgrind-based test suite and to the authors' reading of the generated code.

**How it works at the instruction level**

- **Condition values are masks, not booleans.** `mbedtls_ct_bool(x)` (`constant_time_impl.h:120`) turns any non-zero word into all-ones and zero into all-zeros, so later operations are plain AND/OR/XOR. Helpers such as `mbedtls_ct_if` (`:205`), `mbedtls_ct_uint_lt` (`:271`) and `mbedtls_ct_uchar_in_range_if` (`:391`) are built on that.
- **Assembly where available.** `mbedtls_ct_bool`, `mbedtls_ct_if` and `mbedtls_ct_uint_lt` each have hand-written `asm volatile` branches for AArch64, 32-bit ARM (Thumb-aware), x86-64 and x86-32, selected by `MBEDTLS_CT_*_ASM` and `MBEDTLS_CT_SIZE_32/64`. The asm sequences are `neg/orr/asr`-style mask generation and `and/not/or` selects, so no branch or conditional instruction is emitted.
- **The asm is gated on the platform.** `MBEDTLS_CT_ASM` (`:42`) is defined only when `MBEDTLS_HAVE_ASM` is set (default on, `mbedtls_config.h:52`) and a GNU or ARMCC compiler is detected. I did not read the exact `#if` expression; the index only shows those three macros as its gates.
- **Opacity barrier.** `mbedtls_ct_compiler_opaque` (`:85`) stops the compiler from folding a value it could otherwise prove constant. With asm it is an empty `asm volatile ("" : "+r"(x))`. Without asm it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a global `volatile` set to 0 (`library/constant_time.c:29`), so the compiler must load it at run time.
- **Byte comparison.** `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers to force full reads, ORs the XOR differences, and folds the result so it is non-zero only when the buffers differ. It is explicitly *not* constant-time in `n`.

**What happens on a compiler that cannot support the asm**

- Nothing fails at build time. The `#else` branches are portable C, and the build proceeds.
- The C fallback relies on the `volatile` opacity trick and on arithmetic such as `(-xo) | -(xo >> 1)` to build masks. The source comment says that as of May 2023 trunk clang, gcc and MSVC did not turn these into branches. That is an observation about specific compiler versions, not a guarantee.
- The only hard compile-time guard I found is `#error` in `mbedtls_ct_memcmp` for `int` narrower than 32 bits.
- `SECURITY.md` ("Caveats") says outright that compilers can introduce timing side channels in code meant to be constant-time, and that Mbed TLS makes no guarantee against non-timing local side channels.

**How far it reaches**

The index shows callers in these areas (AST-resolved unless noted):

| Area | Uses of the facility |
|---|---|
| Bignum | `mbedtls_mpi_core_lt_ct`, `check_zero_ct`, `montmul`, `gcd_modinv_odd`, `mpi_safe_cond_assign/swap`, `mod_raw_cond_*`, `ct_mpi_sign_if` |
| RSA | PKCS#1 v1.5 unpadding (`mbedtls_ct_rsaes_pkcs1_v15_unpadding`), OAEP decrypt, PKCS#1 v1.5 sign/verify comparison |
| Block-cipher padding | `mbedtls_get_pkcs_padding` and the cipher padding checks in `cipher.c`, plus `cmac_multiply_by_u` |
| Tag and MAC comparison | GCM, CCM, ChaCha20-Poly1305, NIST KW unwrap, `mbedtls_cipher_check_tag`, PSA MAC/hash verify, PSA cipher finish |
| TLS record and handshake | `mbedtls_ct_hmac` (`ssl_msg.c:65`, a constant-flow MAC-then-verify using PSA hash clone), `ssl_parse_encrypted_pms` (premaster secret decryption), `ssl_parse_finished`, cookie check, TLS 1.3 PSK binder and identity checks |
| Encoding | `mbedtls_ct_base64_enc_char` and `dec_value` in `base64.c` |

**Gaps**

- The symbol search was capped at 60 rows, so the list above may not be exhaustive. For example, I did not confirm EC point code or the rest of the PSA driver paths.
- I found no compile-time or runtime enforcement that code marked constant-time stays that way. The index has no `MBEDTLS_CONSTANT_FLOW` symbol and no code matches for it.
- The test side is `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25`), which runs `tests/suites/*constant_time*.data` under Valgrind and excludes the HMAC data file. That checks for secret-dependent branches and memory access, not timing.
- `3rdparty/p256-m` has its own constant-time design, including a `MUL64_IS_CONSTANT_TIME` switch. It is separate from the `constant_time` module and I did not cover it in depth.