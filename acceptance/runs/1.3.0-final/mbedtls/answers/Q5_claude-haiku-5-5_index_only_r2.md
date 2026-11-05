## Short answer

Constant-time behaviour is not checked by the compiler or by a build-time guarantee. It is a best-effort design: the library hand-writes assembly for a small set of branch-free primitives where the toolchain allows it, falls back to plain C elsewhere, and relies on Valgrind/MemSan runs to catch secret-dependent branches. The facility is used across bignum, RSA, ciphers, MACs/AEAD, and SSL/PSA, but I could not verify every caller from the index.

## How it is enforced at the instruction level

All primitives live in `library/constant_time_impl.h` and are built around a mask: a `mbedtls_ct_condition_t` is either all-ones or all-zeros, so `if` becomes `and/or/not` arithmetic.

- **`mbedtls_ct_bool(x)`** (`constant_time_impl.h:120`) turns any integer into a mask (all-ones if `x != 0`). The AArch64, ARM, x86-64 and x86-32 branches use `neg/orr/asr` (or equivalents) inline assembly. The plain-C fallback is `-x | -(x>>1)` followed by a sign-bit shift, and the header comment notes that trunk clang, gcc and MSVC v19 did not turn it back into branches as of May 2023.
- **`mbedtls_ct_if(cond, a, b)`** (`:205`) selects between two values using `and/not/and/or` in asm, with the same per-architecture split.
- **`mbedtls_ct_uint_lt`** (`:271`) and its relatives (`_eq`, `_ne`, `_gt`, `_ge`, `_le`) are built on these two.
- **`mbedtls_ct_compiler_opaque(x)`** (`:85`) hides a value from the optimizer. In the asm path it is an empty `asm volatile` with `"+r"`; otherwise it XORs with `mbedtls_ct_zero`. It is called from `mbedtls_ct_bool` and `mbedtls_ct_if`, so the compiler cannot prove the mask's value and fold it back into a branch.
- **`mbedtls_ct_memcmp`** (`library/constant_time.c:67`) reads both buffers through `volatile` pointers, XOR-accumulates the differences with no early exit, and folds the result to a non-zero/zero int. The comment says it is not constant with respect to `n`, only the data.

## What happens on a compiler that cannot support it

There is no build failure and no warning. The asm is gated on `MBEDTLS_CT_ASM`, which is defined only when `MBEDTLS_HAVE_ASM` is on and the compiler is GNU-compatible (`__GNUC__`) or ARM Compiler (`__ARMCC_VERSION`) (`constant_time_impl.h:40-52`). Within that, each primitive also requires a matching architecture macro (`__x86_64__`, `__aarch64__`, ARM, x86-32) and a word size (`MBEDTLS_CT_SIZE_32`/`_64`). Anything else, such as MSVC or IAR, compiles the C fallback silently.

So on those toolchains the library gets *the same API with weaker guarantees*. The C fallback relies on the optimizer not recognizing the pattern, which the comments say holds for the tested compilers but is not promised. `SECURITY.md`'s "Caveats" section says in terms that compilers can introduce timing side channels into code meant to be constant-time. Setting `MBEDTLS_HAVE_ASM` off also removes the asm for the whole library, not just these primitives.

One guard is hard, not silent: `mbedtls_ct_memcmp` has `#error` if `int` is narrower than 32 bits, because the sign-folding trick would then lose bits.

## How far it reaches

Callers the index resolved (not exhaustive):

| Area | Examples |
|---|---|
| Bignum | `mbedtls_mpi_core_lt_ct`, `_check_zero_ct`, `_montmul`, `_gcd_modinv_odd`, `_add_if`; `mbedtls_mpi_safe_cond_assign/swap`, `mbedtls_mpi_lt_mpi_ct` |
| RSA | PKCS#1 v1.5 unpadding, OAEP decrypt, `ct_memcmp` in sign/verify |
| Symmetric/AEAD | CMAC multiply, cipher padding removal, GCM, CCM, ChaCha20-Poly1305 tag checks, NIST KW unwrap |
| SSL | encrypted pre-master-secret parse, Finished verification, record decrypt, cookie check, TLS 1.3 PSK binder/identity matching |
| PSA | cipher finish, MAC verify, hash compare, AEAD verify driver wrappers |

The p256-m third-party module is separate: it documents its own constant-time design and a `MUL64_IS_CONSTANT_TIME` switch rather than using `mbedtls_ct_*`.

## How it is tested

- `component_release_test_valgrind_constant_flow` (`tests/scripts/components-sanitizers.sh:72`) builds a release configuration with `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`, runs `make memcheck`, and runs `test_suite_constant_time` under Valgrind on both the asm and plain-C paths. Secret inputs are marked as uninitialized, so a secret-dependent branch or memory index shows up as an uninitialized-value error.
- `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25`) runs the `*constant_time*` suites under Valgrind.

This is dynamic and path-specific: it only checks the code paths the suites exercise, and only in builds that define the test macro.

## Gaps and limits of this answer

- I did not read `SECURITY.md` in full; only its "Caveats" snippet came back.
- I did not confirm the body of the C fallback in `mbedtls_ct_if` beyond its callees, or the definition of `mbedtls_ct_zero`.
- The caller lists are the ones the index resolved, not a proof that every secret-dependent path is covered.
- `TEST_CF_SECRET`/`MBEDTLS_TEST_CONSTANT_FLOW` have no indexed symbols, so the test-side macros are described only from the shell comments.