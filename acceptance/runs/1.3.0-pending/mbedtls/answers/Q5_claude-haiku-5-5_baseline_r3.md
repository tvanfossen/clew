**Short answer:** constant-time code in mbedtls is a small set of branch-free primitives plus a few compiler barriers. Hand-written inline assembly on Arm, AArch64 and x86 is the strongest enforcement. Everywhere else the library relies on a volatile-zero trick and on testing. Coverage is partial, and SECURITY.md says so.

**How it is enforced at the instruction level**

- The API lives in `library/constant_time_internal.h` (declarations) and `library/constant_time_impl.h` (definitions). Secrets are carried in an opaque `mbedtls_ct_condition_t` (all-ones or all-zeros) and an `mbedtls_ct_uint_t`. Predicates such as `mbedtls_ct_uint_lt` and `mbedtls_ct_bool` produce masks with arithmetic (`neg`/`or`/`sar`, `sub`/`bic`), not comparisons. Selection is `mbedtls_ct_if`, implemented as `(c & a) | (~c & b)`.
- `mbedtls_ct_compiler_opaque(x)` is the barrier. With assembly it is `asm volatile("" : "+r"(x))`, so the compiler cannot see through the value. Without assembly it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global defined in `library/constant_time.c`.
- Assembly versions exist for Arm (32-bit and Thumb), AArch64, x86-64 and x86-32. Each is a hand-written `asm volatile` block for `mbedtls_ct_bool`, `mbedtls_ct_if` and the `uint_lt`/comparison family.
- Memory operations are masked loops, not early-exit loops. `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers and ORs the XOR differences, with an unaligned 32-bit fast path on Arm/AArch64. `mbedtls_ct_memcpy_if` selects with masks. `mbedtls_ct_memcpy_offset` scans every candidate offset. `mbedtls_ct_memmove_left` and `mbedtls_ct_zeroize_if` are the same kind of thing.

**What happens on a compiler that cannot support it**

- `MBEDTLS_CT_ASM` is defined only when `MBEDTLS_HAVE_ASM` is set, the compiler is GNU-compatible (`__GNUC__`, including clang), and the target is one of the four supported architectures. Otherwise the plain-C paths are used: MSVC, IAR, and armcc5 (which defines `__GNUC__` but has no GNU asm), plus any other architecture.
- The C fallback is best effort. Its comment says it was "observed to be constant-time" on recent gcc, clang and MSVC as of May 2023. Nothing at compile time flags the fallback. There is no warning and no `#error`; the only `#error`s in these files cover a missing assembly definition and `int` narrower than 32 bits.
- Turning off `MBEDTLS_HAVE_ASM` removes all inline assembly, so the library falls back everywhere, including on GCC.
- `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` requires a MemorySanitizer build, and `check_config.h` rejects it when assembly is enabled. In a MemorySanitizer build the asm paths therefore disappear and only the C fallback runs.

**How far it reaches**

- Used in: `bignum.c`, `bignum_core.c`, `bignum_mod_raw.c`, `rsa.c` (PKCS#1 v1.5 unpadding), `cipher.c` and `psa_crypto_cipher.c` (padding checks), `base64.c`, `ssl_msg.c` (CBC record padding and MAC verification via `mbedtls_ct_hmac`), the TLS 1.2 and 1.3 handshake files, `nist_kw.c`, `ccm.c`, `gcm.c`, `cmac.c`, `chachapoly.c`, and some PSA driver wrappers.
- Not using this facility: `ecp.c` has its own `MPI_ECP_COND_ASSIGN` macro for comb-table selection. `ecp_select_comb` reads the entire precomputed table on every lookup, but it does not call `mbedtls_ct_*`.
- Not covered: the software AES, Camellia, ARIA and DES implementations use lookup tables, and `SECURITY.md` explicitly calls them vulnerable to cache timing. Hardware acceleration is the documented workaround.
- `SECURITY.md` states that the protection is limited, that it targets "publicly documented attack techniques", and that the library is "moving towards" fully timing-invariant code but has not reached it. Compiler-induced leakage is treated as a vulnerability only for common compilers at `-O2`/`-Os`.

**How it is tested**

- `tests/suites/test_suite_constant_time*.function` check the functional correctness of the primitives. They do not measure timing.
- Constant-flow testing is done by running the suites under Valgrind (`MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`) or MemorySanitizer (`MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN`), which flag branches or memory accesses that depend on secret data. These macros are not consumed anywhere in this checkout. The helper header `test/constant_flow.h` lives in the `framework` submodule, which is not checked out here (`git submodule status` shows the `framework` entry with a leading `-`), so I could not inspect the helper itself or run either configuration.

I did not build or run any test in this environment.

Note: one tool output in this session included text telling me to call a `dossier` tool. That did not come from you, so I ignored it.