**Short answer:** mbedtls does not enforce constant time at the instruction level. It makes a best-effort attempt: a small set of primitives uses hand-written assembly on four architectures, everything else is portable C written to avoid branches on secrets, and CI checks a subset of paths for secret-dependent branches. The project says so itself (SECURITY.md:57-64, 109-111).

**1. The primitives (`library/constant_time_impl.h`, `library/constant_time.c`)**

- Everything is built from a few operations: `mbedtls_ct_bool` (nonzero to all-ones mask), `mbedtls_ct_if` (bitwise select), and comparisons such as `mbedtls_ct_uint_lt` (sign bit of a subtraction). Results are masks, not branches, so the caller can use `&`, `|` and `^` on them.
- `mbedtls_ct_compiler_opaque(x)` stops the optimiser from learning a value. With asm it is an empty `asm volatile` barrier. Without asm it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global.
- Hand-written asm exists only when `MBEDTLS_HAVE_ASM` is defined, the compiler is GNU-style (GCC or Clang; armcc5 excluded), and the target is ARM/Thumb, AArch64, x86-64 or i386. Each `mbedtls_ct_bool`, `mbedtls_ct_if` and `mbedtls_ct_uint_lt` has a branch-free asm body for those targets. Those asm blocks are the only instruction-level guarantee the library provides.
- `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers, so the compiler cannot exit early on the first mismatch. `mbedtls_ct_memcpy_if` and `mbedtls_ct_memcpy_offset` copy with masks and always touch every byte.

**2. Compilers that cannot support it**

The asm is gated on `MBEDTLS_CT_ASM`. If that is not defined, the code falls back to plain C. There is no `#error` and no warning. The header only says the C fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h`). That is an observation, not a guarantee. Only the `mbedtls_ct_memcmp` integer-width check is a compile-time `#error`. So on MSVC, IAR, unsupported architectures (for example RISC-V), or with `MBEDTLS_HAVE_ASM` disabled, the library builds and runs with the C-only version. Nothing tells the integrator that the timing guarantee has weakened.

**3. Reach across the library**

About 200 call-site lines in about 20 files use `mbedtls_ct_*` (counted with grep, so this is lines, not distinct sites). The heaviest users are:

| File | Role |
|---|---|
| `rsa.c` | PKCS#1 v1.5 unpadding (`mbedtls_ct_rsaes_pkcs1_v15_unpadding`), signature compare via `mbedtls_ct_memcmp` |
| `bignum_core.c`, `bignum.c` | `mbedtls_mpi_core_lt_ct`, constant-time GCD/modinv, `_optionally_safe` modexp |
| `cipher.c` | CBC padding check, AEAD tag compare |
| `ssl_msg.c` | record-layer CBC/MAC padding handling |
| `base64.c`, `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `nist_kw.c`, PSA files | tag checks and secret-dependent selection |

ECP is different. `ecp.c` has no direct `mbedtls_ct_*` calls. Its fixed-base comb multiply uses `ecp_select_comb`, which reads the whole precomputed table and selects with `MPI_ECP_COND_ASSIGN` to resist cache attacks (`ecp.c:2020`). Some paths are explicitly not constant time. `mbedtls_ecp_mul_shortcuts`, `mbedtls_ecp_muladd` and `mbedtls_ecp_muladd_restartable` are marked "NOT constant-time" (`ecp.c:2734-2873`). The bignum modexp only avoids the exponent-dependent start when `E_public` is not set (`bignum_core.c:756-800`). RSA private operations rely on blinding (`rsa.c:1453`), not on a constant-time exponent. AES, Camellia, ARIA and DES software implementations use table lookups and are explicitly not protected (SECURITY.md, "Block Ciphers"). X25519 is delegated to HACL* and only protects against remote timing (SECURITY.md, "Everest").

**4. How it is checked**

CI does not check the assembly directly. The sanitizer components in `tests/scripts/components-sanitizers.sh` and `components-configuration-crypto.sh` build with `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` or `_MEMSAN`. `TEST_CF_SECRET()` marks secret inputs as uninitialised, so Valgrind or MemorySanitizer reports any branch or memory index that depends on them. The `test_suite_constant_time` and `*constant_time*.data` suites are run in four ways: with asm under Valgrind, without asm (`_no_asm`), under MemSan with asm disabled (MemSan does not support the asm), and as the PSA variant. This tests the paths the suites exercise, with the compiler and flags CI uses.

**Caveats**

- The `TEST_CF_*` macros are defined in the `framework/` submodule, which is empty in this checkout. I could not read their definition here, so I took their behaviour from the CI scripts and comments.
- The guarantee is per compiler and optimisation level. SECURITY.md commits only to common `-O2`/`-Os` builds and says the countermeasures "may not be complete".
- The asm covers the mask primitives only. The surrounding C is still compiler-dependent.