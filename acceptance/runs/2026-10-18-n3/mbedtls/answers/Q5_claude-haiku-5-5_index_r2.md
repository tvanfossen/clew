**Short answer:** nothing in the build checks constant time. The library uses a set of branch-free primitives, hand-written assembly on the main architectures, and a C fallback elsewhere. The guarantee comes from construction plus Valgrind/MSan tests, and the project's own SECURITY.md says the protection is limited.

## How it works at the instruction level

The primitives live in `library/constant_time_impl.h` and are built on two ideas:

1. **Hide the value from the optimizer.** `mbedtls_ct_compiler_opaque()` (`constant_time_impl.h:85-93`) is an empty `asm volatile("" : "+r"(x))` when assembly is available. Otherwise it returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global holding 0 (`constant_time.c:29`). Either way the compiler cannot prove what the value is, so it cannot rewrite the code as a branch.
2. **Compute with masks, not comparisons.** A condition is an all-ones or all-zeros word. For example, `mbedtls_ct_bool` turns "x ≠ 0" into a mask with `-x | -(x>>1)` and a sign-bit extraction (`constant_time_impl.h:120-203`). `mbedtls_ct_if` selects with `(c & a) | (~c & b)`. `mbedtls_ct_uint_lt` compares the MSBs and then uses a subtraction (`:271-380`).

On top of the scalar operations, the block helpers in `constant_time.c` read every byte regardless of the secret: `mbedtls_ct_memcpy_if`, `mbedtls_ct_memcpy_offset` (loops over all candidate offsets), `mbedtls_ct_memmove_left`, `mbedtls_ct_zeroize_if`, and `mbedtls_ct_memcmp`. `memcmp` casts both buffers to `volatile` so the compiler cannot exit early on the first difference (`constant_time.c:78-79`).

The assembly versions are selected by `constant_time_impl.h:40-51`. They are used only when `MBEDTLS_HAVE_ASM` is set, the compiler is GCC-compatible (Clang included), and the target is 32-bit Arm/Thumb, AArch64, x86-64 or x86-32. Each asm body is further gated on word size, so a given target might get asm for one operation and C for another. The default config defines `MBEDTLS_HAVE_ASM` (`include/mbedtls/mbedtls_config.h:52`).

I did not disassemble any build, so I have not confirmed that the compiler preserves these sequences in the emitted code.

## What happens on a compiler that cannot support it

- **Silent fallback.** If `MBEDTLS_CT_ASM` is not defined, the C versions are used. There is no `#error` and no warning. The only compile-time check in this area concerns integer width (`constant_time.c:99-105`).
- **Fallback behaviour.** The C path depends on the volatile-zero trick and on the optimizer not turning the arithmetic into branches. The header says this has been "observed to be constant-time" on recent gcc, clang and MSVC as of May 2023 (`constant_time_internal.h:55-59`). That is an observation, not a guarantee.
- **Slower fallback.** The unaligned fast path in `memcmp` and `memcpy_if` is only enabled for Arm/AArch64 asm (`constant_time.c:42-46`), so the fallback works byte by byte. The header also calls the opaque barrier "fairly inefficient".
- **Config interaction.** `MBEDTLS_HAVE_INT32`/`MBEDTLS_HAVE_INT64` cannot be combined with `MBEDTLS_HAVE_ASM` (`check_config.h:1063-1066`). Builds on those limb settings therefore lose the asm path entirely.
- **Security posture.** SECURITY.md says compilers "can introduce timing side channels in code that was intended to be constant-time", that prevention "may not be complete", and that the project only treats issues as vulnerabilities at `-O2`/`-Os` (`SECURITY.md:107-111`). `-O3` and `-Oz` get less scrutiny.

## How far it reaches

- **Public surface.** Only `mbedtls_ct_memcmp` is public (`include/mbedtls/constant_time.h`). Everything else is in `library/constant_time_internal.h`, which is internal. The bignum core also exposes `_ct` functions such as `mbedtls_mpi_core_lt_ct` and `mbedtls_mpi_core_check_zero_ct`.
- **Consumers.** About 396 occurrences across 29 files in `library/`, excluding the `constant_time*` files themselves. Representative uses:

| Area | Where |
|---|---|
| TLS record MAC check and CBC padding handling | `ssl_msg.c:147, 250, 1798, 2060-2071` |
| TLS 1.2 Finished and PSK binder checks | `ssl_tls12_client.c:627`, `ssl_tls13_server.c:451` |
| TLS 1.2 premaster-secret selection | `ssl_tls12_server.c:3474` |
| RSA PKCS#1 v1.5 unpadding | `rsa.c:503, 519` |
| RSA OAEP and PSS checks | `rsa.c:2049, 2774` |
| AEAD tag comparisons | `gcm.c:760`, `ccm.c:590`, `chachapoly.c:320`, `cipher.c:1298, 1319` |
| PSA MAC and hash verify | `psa_crypto_mac.c:445`, `psa_crypto.c:3013` |
| Bignum core | `bignum_core.c:576` |
| NIST KW | `nist_kw.c:358-422` |

- **Not everywhere.** Plain `memcmp` is still common, mostly on public data such as OIDs, certificate fields, session IDs and cache lookups. I sampled these rather than auditing each site, so I cannot rule out a secret-dependent plain `memcmp` somewhere.
- **Outside the facility.** `3rdparty/p256-m` has its own constant-time design (`MUL64_IS_CONSTANT_TIME`, Fermat inversion). It is not built on `mbedtls_ct_*`.
- **Block ciphers.** SECURITY.md states that block ciphers "do not yet achieve full protection" (`SECURITY.md:72-73`). I did not read that section, so I cannot say which parts are affected.

## How it is tested

- **Functional tests.** `test_suite_constant_time` and `test_suite_psa_crypto_constant_time` check results only, not timing.
- **Constant-flow tests.** These are the real enforcement. Secrets are annotated with `TEST_CF_SECRET`. Under Valgrind (`MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`) or MSan (`MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN`), any branch or memory address that depends on a secret is reported as an error. Suites without `TEST_CF_` annotations are skipped (`components-sanitizers.sh:12-21`).
- **No-asm coverage.** `component_release_test_valgrind_constant_flow_no_asm` (`components-sanitizers.sh:105-127`) runs the same checks with `MBEDTLS_HAVE_ASM` unset, so the C fallback is tested this way too.
- **Limits.** These tools catch secret-dependent control flow and addresses on the tested path. They do not measure cache or instruction timing on real hardware, which is where SECURITY.md says the remaining risk sits.