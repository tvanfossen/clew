## Short answer

Constant-time code in mbedtls is a set of primitives in `library/constant_time_impl.h`. On GCC/Clang for Arm, AArch64, x86 and x86-64, each primitive is hand-written inline assembly, so the instruction sequence is fixed. Everywhere else, including MSVC and any build with `MBEDTLS_HAVE_ASM` undefined, the primitives fall back to plain C. That fallback has no compile-time check and is only argued to be constant-time. The primitives are used in roughly 25 library files, mostly for TLS record MAC and padding checks, RSA/PKCS#1 unpadding, tag comparisons, and bignum/ECP scalar handling. The library's own security policy says it has not reached full timing invariance.

## How it is enforced at the instruction level

- **Opaque condition values.** `mbedtls_ct_condition_t` is an all-zeros or all-ones mask. Operations such as `mbedtls_ct_bool`, `mbedtls_ct_uint_eq` and `mbedtls_ct_if` are built from `and`/`or`/`neg`/`sar`, so there is no branch to take (`constant_time_impl.h:130-200`).
- **Hiding values from the optimiser.** `mbedtls_ct_compiler_opaque()` wraps values in an empty `asm volatile` block so the compiler cannot prove anything about a condition. Without asm it XORs with a `volatile` zero, `mbedtls_ct_zero` (`constant_time_impl.h:68-92`, `constant_time.c:29`).
- **Assembly per architecture.** The `MBEDTLS_CT_*_ASM` macros pick an assembly path (`constant_time_impl.h:40-50`). Each `mbedtls_ct_*` function has an arm, AArch64, x86-64 and i386 variant with explicit register constraints. Some use `asm volatile` and some rely on the register constraints alone.
- **Block operations.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers and accumulates XOR differences, so the compiler cannot exit early (`constant_time.c:~60-100`). `mbedtls_ct_memcpy_if` and `mbedtls_ct_zeroize_if` do a read and write of every byte regardless of the condition (`constant_time.c:~170-246`).
- **Table reads.** `ecp_select_comb` reads the whole precomputed table and selects with `MPI_ECP_COND_ASSIGN` (`ecp.c:2010-2030`), so the cache-access pattern does not depend on the secret index.

## What happens on a compiler that cannot support it

The asm path is gated by `MBEDTLS_HAVE_ASM && defined(__GNUC__)` plus an architecture match (`constant_time_impl.h:40`). If either fails, the code takes the C branch. There is:

- **No `#error` and no warning.** The build succeeds silently.
- **No functional change.** The results are the same; only the timing guarantee is weaker.
- **A weaker guarantee.** The comment says the C fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h`). That is an observation, not a guarantee; a future compiler can introduce a branch.
- **An explicit opt-out.** Undefining `MBEDTLS_HAVE_ASM` (`mbedtls_config.h:52`) also forces the C path on GCC, which is how you get it on a supported compiler.

`SECURITY.md` (Compiler-induced side channels) states that the mitigation "may not be complete" across compilers and flags, and that they only treat exploitable leaks at common levels (`-O2`, `-Os`) as vulnerabilities.

## How far it reaches

| Area | Where | Notes |
|---|---|---|
| TLS record MAC verify, Lucky13-style | `ssl_msg.c` (`mbedtls_ct_hmac`, `ct_memcpy_offset`, `ct_memcmp` at ~2071) | Uses ct memcpy to hide the MAC data position. |
| CBC padding removal | `cipher.c:861-1000`, `ssl_msg.c:1916-1978` | PKCS#7, zero-padding and one-and-zeros variants. |
| RSA PKCS#1 v1.5 unpadding | `rsa.c:420-480` | Bleichenbacher-style checks in constant time. |
| TLS 1.2 PMS fallback | `ssl_tls12_server.c:3409-3474` | Substitutes a fake PMS without branching. |
| Tag and MAC comparisons | `gcm.c:760`, `ccm.c:590`, `chachapoly.c:320`, `cmac`, `psa_crypto_mac.c:445`, `nist_kw.c` | All use `mbedtls_ct_memcmp`. |
| Bignum core | `bignum_core.c` (`lt_ct`, `check_zero_ct`, swaps), `bignum.c` | Used in modular ops and inversion. |
| ECP | `ecp.c` comb multiplication, `ecp_select_comb` | `mbedtls_ecp_mul_shortcuts` and `muladd_restartable` are labelled NOT constant-time. |
| Base64 | `base64.c` | Decode path. |

What is **not** covered:

- **Length.** `mbedtls_ct_memcmp` is explicitly not constant-time in `n` (`constant_time.h`).
- **Public control flow.** Loop bounds and branches on public values remain ordinary C.
- **Block ciphers.** `SECURITY.md` warns that they "do not yet achieve full protection."
- **Physical and local side channels.** These are out of scope (`SECURITY.md`).

## How it is tested

Opt-in only. `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` and `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (`mbedtls_config.h:2109-2142`) make tests mark secrets and then run under MemorySanitizer or Valgrind memcheck. The CI components are `components-sanitizers.sh` and `components-configuration-crypto.sh`, plus `test_suite_constant_time*.data`. The `TEST_CF_SECRET` and `TEST_CF_PUBLIC` macros live in `framework/tests/include/test/constant_flow.h`, which is a git submodule that is empty in this checkout, so I could not read them and did not verify the marking mechanism.

## Caveat

I read the code and config but did not build or run anything, so I have not checked the generated assembly or confirmed the MSan/Valgrind jobs pass.