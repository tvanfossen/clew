**Short answer:** mbedtls does not enforce constant time in the compiler. It hand-writes the few primitives that matter in assembly where it can, falls back to C that is only *observed* to be branch-free, and checks the result dynamically with Valgrind and MSan. The facility reaches into bignum, RSA, TLS record handling and the symmetric/AEAD tag checks. ECC is largely outside the ct helpers.

**1. How it is enforced at the instruction level**

All the primitives live in `library/constant_time_impl.h`. Secret values travel as `mbedtls_ct_condition_t`, an all-ones or all-zeros mask. Operations are arithmetic on that mask, so there is no branch to take:

- `mbedtls_ct_bool(x)` turns `x != 0` into a mask. On x86-64 it is `mov; neg; or; sar $63` (`constant_time_impl.h:157-168`).
- `mbedtls_ct_if(c, a, b)` selects with `and/not/and/or`. On x86-64 that is `and; not; and; or` (`:238-250`).
- `mbedtls_ct_uint_lt` is a sub/xor/and/sar sequence with no `cmp` + `jcc` (`:314-331`).

Those asm blocks exist for AArch64, 32-bit Arm, x86-64 and i386. The compiler cannot re-introduce a branch inside an `asm volatile` block.

The compiler is kept from *proving* values, which would let it fold secret-dependent code, by `mbedtls_ct_compiler_opaque`. With assembly it is an empty `asm volatile("" : "+r"(x))`. Without assembly it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global (`constant_time_impl.h:85-93`, `library/constant_time.c:29`).

Verification is dynamic, not static. The test harness marks secrets as undefined (`TEST_CF_SECRET`). Valgrind memcheck or MSan then reports any secret-dependent branch or memory index as an uninitialised-value use. The components are `component_release_test_valgrind_constant_flow`, `..._memsan_constant_flow`, and the `_no_asm` variant (`tests/scripts/components-sanitizers.sh:33-129`), plus `test_with_valgrind_constant_time` over `tests/suites/*constant_time*.data` (`tests/scripts/components-configuration-crypto.sh:25-33`).

Caveat: `constant_flow.h` (where `TEST_CF_SECRET` is defined) is not present in this checkout, so I could not read the marking macros. This check only covers code paths the test inputs exercise, and only on the compiled binary.

**2. A compiler that cannot support it**

The gate is in `constant_time_impl.h:40-52`. Assembly is used only when `MBEDTLS_HAVE_ASM` is set, the compiler is GNU-compatible (`__GNUC__`), and it is not old armcc. Within that, the arch macro must match one of the four listed. Anything else gets the plain C fallback:

| Build | Result |
|---|---|
| MSVC, or `MBEDTLS_HAVE_ASM` undefined | C fallback, no error |
| Unlisted arch (RISC-V, MIPS, etc.) | C fallback, no error |
| Asm arch, but size combo not matched (e.g. 64-bit Arm without the 32-bit case) | C fallback for that primitive |

There is no `#error` for missing asm. The only hard error in this area is `mbedtls_ct_memcmp` requiring at least 32-bit ints (`library/constant_time.c:105`).

The C fallback is a claim, not a guarantee. The header says it "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h:55-59`). It is also called "fairly inefficient" in its own comments. The CI component that exercises the no-asm path is the only evidence that it stays branch-free, so a new compiler version could silently break it.

**3. How far it reaches**

A text count finds about 444 matches for `mbedtls_ct_|constant_time` across 35 library files. That count includes `#include` lines, so it is not a call count. The heaviest users are:

- `rsa.c` (39): PKCS#1 v1.5 unpadding, with branch-free scanning and padding checks.
- `cipher.c` (32), `bignum_core.c` (34), `bignum.c` (27): CBC/padding and bignum comparisons.
- `ssl_msg.c` (26): record MAC handling via `mbedtls_ct_hmac`, which pads and hashes in a fixed pattern, plus `mbedtls_ct_memcmp` on the tag.
- `base64.c` (22), `psa_crypto.c` (11), `ssl_tls12_server.c` (10), `nist_kw.c` (6).
- AEAD tag compares in `gcm.c`, `ccm.c`, `cmac.c`, `chachapoly.c` (2 each).

ECC is the notable gap. `ecp.c` contains no `mbedtls_ct_` helper calls. Its constant-time behaviour comes from `bignum_core` routines and `mbedtls_mpi_safe_cond_assign` in the comb recoding (`ecp.c:2140-2143`). Some `ecp.c` functions are explicitly commented "NOT constant-time" (around lines 2734, 2769, 2873). I did not trace their callers to see whether they handle secrets.

So the facility covers the secret-bearing paths in RSA, symmetric/AEAD padding and tags, TLS record MAC checks and the bignum primitives. It does not cover ECC scalar multiplication through this helper layer. The dynamic check only validates what the tests exercise.