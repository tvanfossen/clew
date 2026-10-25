**Short answer:** constant-time behaviour is enforced by writing secret-dependent logic as bit masks, not by a compiler guarantee. On GCC/Clang for Arm, AArch64, x86 and x86-64, the mask primitives are inline assembly, so the optimizer cannot turn them back into branches. Everywhere else, the library silently falls back to plain C that is only "observed" to be constant-time. The facility is limited to specific hotspots, and the library's own security doc says timing protection is incomplete.

**How it is enforced at the instruction level**

- The primitives live in `library/constant_time_impl.h`, with declarations in `library/constant_time_internal.h`. Condition values are all-ones or all-zeros masks (`mbedtls_ct_condition_t`), and operations such as `mbedtls_ct_bool`, `mbedtls_ct_uint_eq`, `mbedtls_ct_if` and `mbedtls_ct_memcpy_if` combine them with AND/OR/NOT.
- On x86-64, `mbedtls_ct_bool` is `mov; neg; or; sar $63`, which yields all-ones iff the input is non-zero. `mbedtls_ct_if` is `and; not; and; or`. AArch64 and 32-bit Arm have equivalent sequences.
- `mbedtls_ct_compiler_opaque()` stops the compiler from learning a value. With asm it is an empty `asm volatile` with a `+r` constraint. Without asm it XORs with `mbedtls_ct_zero`, a `volatile` zero the compiler cannot fold.
- `mbedtls_ct_memcmp()` in `library/constant_time.c` reads both buffers through `volatile` pointers, ORs all differences together, and never exits early. Only `n` may leak, as the public header in `include/mbedtls/constant_time.h` documents.
- The guarantee is narrower than it looks. Asm covers the mask and select primitives. Callers still write ordinary C around them, and the rule that secrets must flow only through these primitives is enforced by code review, not by the toolchain.

**What happens on a compiler without support**

- Asm is used only when `MBEDTLS_HAVE_ASM` is defined and `__GNUC__` is present, and not for ARMCC older than 6. Clang passes that check because it defines `__GNUC__`. MSVC, ARMCC 5, and any unlisted architecture (for example RISC-V) get the C fallback.
- The fallback is branch-free C. For example, `mbedtls_ct_bool` uses `(-x | -(x>>1)) >> (bits-1)`. It is not guaranteed to stay branch-free, and the code comment says only that it was observed to be so on "latest gcc, clang and MSVC as of May 2023."
- There is no `#error` or warning when asm is unavailable. The only hard `#error` in this area is for `int` narrower than 32 bits. Degradation is silent.
- CI covers the fallback. `tests/scripts/components-sanitizers.sh` has `component_release_test_valgrind_constant_flow_no_asm` alongside the asm variant, and `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` and `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` make the tests fail on secret-dependent control flow. Those are dynamic checks on the tested paths, not proofs.

**How far it reaches**

The only public symbol is `mbedtls_ct_memcmp`. Everything else is internal. Users of the call sites I checked:

| Area | Where | Purpose |
|---|---|---|
| TLS record layer | `library/ssl_msg.c` | Constant-time HMAC over the record, padding check, MAC compare (`mbedtls_ct_hmac`, `mbedtls_ct_memcmp`) |
| RSA PKCS#1 v1.5 | `library/rsa.c` | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` (Bleichenbacher-style checks) |
| Symmetric padding and tags | `library/cipher.c` | PKCS#7, zero and one-and-zeros padding removal; tag compares |
| Bignum | `library/bignum_core.c`, `bignum.c`, `bignum_mod*.c` | Constant-time comparisons and selects |
| ECC fixed-base | `library/ecp.c` | Comb recoding and `ecp_select_comb` on `ecp_mul_comb` |
| Other | `base64.c`, `nist_kw.c`, `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `ssl_cookie.c`, PSA files | Assorted secret-dependent checks |

Things it does not cover:

- `mbedtls_ecp_mul_shortcuts` in `ecp.c` is explicitly marked "NOT constant-time." The variable-base comments at `ecp.c` ~2734 and ~2769 say the same.
- `SECURITY.md` says block ciphers do not yet achieve full timing protection, and that cache and branch-prediction timing attacks get only "limited protection." It says the library makes no guarantees against non-timing local side channels or fault injection, and that it is "moving towards" fully timing-invariant code.

Caveat: I read the code and CI scripts but did not build or run any tests, so the statements about the fallback and test coverage are based on reading the source.