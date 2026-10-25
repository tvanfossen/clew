**Short answer:** constant-time behaviour is enforced by coding style and hand-written assembly, not by the compiler. Every constant-time primitive is written as branch-free mask arithmetic. On GCC/Clang-compatible targets, the core mask operations are pinned in inline assembly. Everywhere else, the same C runs with no guarantee. Testing (Valgrind/MSan) is the only check that catches a regression.

**1. How it's enforced at the instruction level**

- The primitives live in `library/constant_time_impl.h` and `library/constant_time_internal.h`, with the public API in `include/mbedtls/constant_time.h`.
- A condition is a mask: all-ones for true, zero for false. `mbedtls_ct_bool()` turns any value into a mask with a `neg`/`or`/`asr` sequence, with no branch.
- `mbedtls_ct_if()` selects between two values with `and`/`not`/`and`/`or`, again with no branch.
- `mbedtls_ct_compiler_opaque()` is an empty `asm volatile` barrier, so the optimizer cannot prove the value of a mask and rewrite it into a branch.
- Each primitive has hand-written asm for ARM (Thumb-aware), AArch64, x86-64 and x86. These paths are selected by `MBEDTLS_CT_{ARM,AARCH64,X86_64,X86}_ASM` plus a 32- or 64-bit size macro.
- `mbedtls_ct_memcmp()` reads through `volatile` pointers and XORs every byte, with no early exit. On ARM/AArch64 it uses volatile unaligned word loads for speed.
- Higher-level operations (eq, lt, select on secret values, RSA padding checks, CBC padding removal) are built from these masks. For example, `rsa.c` accumulates a `bad` mask rather than branching on each padding check.

**2. A compiler that can't support it**

- The asm path requires `MBEDTLS_HAVE_ASM` and `__GNUC__`. Some compilers, such as MSVC and IAR, and old armcc5 fail that test.
- When it fails, `MBEDTLS_CT_ASM` is undefined and the plain-C fallback is compiled. `mbedtls_ct_compiler_opaque()` becomes `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global.
- There is no `#error` or warning. The degradation is silent.
- The C fallback's comment says it was checked as of May 2023 with trunk Clang, GCC and MSVC and not optimised into branches. Nothing in the build stops a future optimiser from doing so.
- The one hard rule is in `check_config.h`: MemorySanitizer combined with `MBEDTLS_HAVE_ASM` is a compile-time `#error`. So MSan builds must disable asm.

**3. How far it reaches**

Counts of `mbedtls_ct_` references under `library/`:

| File | Refs | Role |
|---|---|---|
| `rsa.c` | 37 | PKCS#1 v1.5 / OAEP padding checks |
| `bignum_core.c` | 32 | Core bignum (plus 6 in `bignum_core.h`) |
| `cipher.c` | 30 | CBC padding |
| `bignum.c` | 26 | Bignum wrappers |
| `ssl_msg.c` | 24 | TLS record CBC padding and MAC handling |
| `base64.c` | 21 | Base64 decoding of secret data |
| `psa_crypto.c` | 9 | PSA paths |
| `nist_kw.c`, `ssl_tls12_*`, `ssl_tls13_*`, `ssl_cookie.c`, `ssl_tls.c`, `ccm.c`, `gcm.c`, `cmac.c`, `chachapoly.c`, and others | 1–8 each | Assorted |

About 28 library `.c` files use the API. Points to note:

- Coverage is selective. `ecp.c` matched my grep only on comment text, and I did not verify its scalar-multiplication path, so I can't say whether it is constant-time in this sense.
- `3rdparty/p256-m` and `3rdparty/everest` are separate constant-time implementations with their own code.
- The primitives address secret-dependent control flow and memory addresses only. They do not stop cache-timing attacks on table lookups, and they do not cover variable-time division or other instructions.

**4. How it's verified**

- Test suites annotate secrets with `TEST_CF_SECRET` and `TEST_CF_PUBLIC`. There are 94 uses across the suites, including `test_suite_constant_time`, `bignum_core`, `pkcs1_v15`, `base64` and `cipher`.
- The macros are defined in the test framework. In this checkout `framework/` is empty, so I could not read their definitions.
- Under `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` or `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN`, secrets are marked undefined or tainted. Any branch or memory access that depends on them is then reported.
- Both options are commented out in `mbedtls_config.h`, so they are off by default.
- CI runs them in `tests/scripts/components-sanitizers.sh`: `component_test_memsan_constant_flow`, `component_release_test_valgrind_constant_flow`, and a `_no_asm` variant. The no-asm variant exercises the C fallback.