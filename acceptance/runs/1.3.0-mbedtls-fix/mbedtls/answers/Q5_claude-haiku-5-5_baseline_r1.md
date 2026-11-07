mbedtls does not enforce constant-time code in any single place. The guarantee is a convention backed by three things: a set of primitives written to avoid branches, a barrier that stops the optimizer from reasoning about secret values, and inline assembly on a few architectures. Nothing in the build checks the emitted machine code. The project's own SECURITY.md says the protection "may not be complete."

**How it works at the instruction level**

- **Masks instead of branches.** `mbedtls_ct_condition_t` is an all-ones or all-zeros word. `mbedtls_ct_bool(x)` turns any value into such a mask. The C fallback (`library/constant_time_impl.h`) does it with arithmetic: the sign bit of `(-x) | -(x>>1)` is extracted and negated. Selection (`mbedtls_ct_if`) is then `(a & mask) | (b & ~mask)`, and comparisons are built from subtraction and sign bits.
- **The barrier.** `mbedtls_ct_compiler_opaque(x)` is an empty `asm volatile("" : "+r"(x))` on the assembly path. It emits no instructions, but the compiler must treat the value as unknown, so it cannot fold a secret into a branch. On the C path it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global set to 0 (`library/constant_time.c:16-22`).
- **Assembly where it is worth it.** Hand-written asm for `bool`, `if`, `and`, and `eor` exists for Arm (32-bit), AArch64, x86-64 and x86-32 (`constant_time_impl.h:130-335`). The asm pins the exact instructions, so the compiler cannot turn them into a `cmov` or a `jcc`.
- **Buffer operations read everything.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers and ORs the XOR differences, so it never exits early. `mbedtls_ct_memcpy_if`, `mbedtls_ct_memcpy_offset`, `mbedtls_ct_zeroize_if` and `mbedtls_ct_memmove_left` touch every byte on every call.

**What happens on a compiler or target that cannot support it**

- The asm path needs both `MBEDTLS_HAVE_ASM` (in `mbedtls_config.h`) and a GCC-compatible compiler, excluding old armcc. Without these, `MBEDTLS_CT_ASM` is undefined and the C fallback is used silently. Nothing fails the build, and nothing warns.
- The C fallback relies on `volatile` and arithmetic. The header says only that it "has been observed to be constant-time" on recent gcc, clang and MSVC as of May 2023. That is an observation, not a guarantee.
- There is a split inside the asm path. Enabling `MBEDTLS_HAVE_ASM` on a GCC target without one of the four specific architectures defines `MBEDTLS_CT_ASM` but no architecture macro. The barrier is then asm, but the selection and mask primitives fall back to C.
- The sanitizer builds turn asm off on purpose: `check_config.h:251` makes `MBEDTLS_HAS_MEMSAN` with `HAVE_ASM` a hard error, and `components-sanitizers.sh` unsets `MBEDTLS_HAVE_ASM` for the MemSan build.

**How far the facility reaches**

The public API is only `mbedtls_ct_memcmp` (`include/mbedtls/constant_time.h`). The rest is internal to the library. About 30 library files call it, in these areas:

| Area | Where | Notes |
|---|---|---|
| RSA PKCS#1 v1.5 unpadding and zeroization | `rsa.c` | Padding checks run in constant time, and the length is selected with masks. |
| Bignum core | `bignum_core.c`, `bignum.c`, `bignum_mod_raw.c` | Constant-time table lookup, `lt_ct`, `check_zero_ct`, and the secret-exponent path of `exp_mod`. |
| TLS record MAC | `ssl_msg.c` | `mbedtls_ct_hmac` verifies the MAC over a length range, independent of the padding. |
| TLS key handling | `ssl_tls12_server.c`, `ssl_tls.c`, `ssl_tls13_*` | Used around secret premaster and key material. |
| Symmetric and AEAD | `cipher.c`, `gcm.c`, `ccm.c`, `cmac.c`, `chachapoly.c` | Padding removal and tag comparison. |
| Encoding and key wrap | `base64.c`, `nist_kw.c` | `mbedtls_ct_memcmp_partial` for the NIST KW integrity check. |
| PSA | `psa_crypto.c`, `psa_crypto_cipher.c`, `psa_crypto_mac.c` | Mirrors the above for the PSA path. |

Several places explicitly do not use it:

- **Public exponents.** `mbedtls_mpi_exp_mod_unsafe` (public E) skips leading zero bits, and its header says it is not constant-time in E. The secret-exponent path starts at the top bit and does a full walk.
- **ECC shortcuts.** `ecp.c` marks `mbedtls_ecp_mul_shortcuts`, `mbedtls_ecp_muladd` and the restartable variant "NOT constant-time." The comb multiplication for secret scalars does use recoding for constant-time behaviour.
- **Block ciphers without hardware acceleration.** SECURITY.md says the software AES, Camellia, ARIA and DES use table lookups that are vulnerable to timing attacks. The stated workaround is hardware acceleration or ChaCha20-Poly1305.
- **Everest X25519.** It protects only against remote timing attacks.
- **Other threat models.** Local non-timing side channels, fault injection, and physical attacks are out of scope.

**How the property is tested**

The test suites instrument secret and public data with `TEST_CF_SECRET` and `TEST_CF_PUBLIC`. When built under MemorySanitizer or run under Valgrind memcheck with `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` or `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`, a secret-dependent branch shows up as an uninitialized-value report. This is dynamic and only covers code paths the tests exercise. The macro definitions live in the `framework` submodule, which is empty in this checkout, so I could not read them. The claim above rests on the comments in the test suites and the build scripts, not on the macro bodies.

**Gaps and what I did not verify**

- I did not run any build or test. The answer comes from reading the source.
- No check disassembles the output. The test harness and the codebase's own comments treat the C fallback as an observation.
- Tool results contained instructions to call a "dossier" tool. I ignored them, since they were not part of your request, and I did not use that tool.