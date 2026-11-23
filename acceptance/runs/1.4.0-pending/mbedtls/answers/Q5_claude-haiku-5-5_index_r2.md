**Short answer:** the facility is a set of C wrappers over a small "condition" type, with hand-written inline assembly for four ISAs. Nothing in the build proves the generated code is branch-free. On other compilers or targets it silently falls back to plain C. Its reach is bignum, RSA, cipher/CBC padding, the TLS record and PMS paths, and the MAC/tag comparisons. AES and the ECC curve-arithmetic core do not call it directly.

**How it is enforced at the instruction level**

- **Opaque condition type.** `mbedtls_ct_condition_t` is an unsigned integer that is either all-zeros or all-ones (`constant_time_internal.h:65-86`). Callers never write `if (secret)`. They combine conditions with `mbedtls_ct_bool_and/or/not`, select with `mbedtls_ct_if`, and derive them with `mbedtls_ct_uint_lt/ne/eq` and similar.
- **Hiding values from the optimizer.** `mbedtls_ct_compiler_opaque()` (`constant_time_impl.h:85-93`) is an empty `asm volatile` with a read-write register constraint. The compiler cannot see through it, so it cannot fold the value or turn the mask arithmetic back into a branch.
- **Assembly for mask generation and selection.** With `MBEDTLS_CT_ASM` defined, `mbedtls_ct_bool`, `mbedtls_ct_if` and `mbedtls_ct_uint_lt` have hand-written `asm volatile` bodies for AArch64, 32-bit Arm/Thumb, x86-64 and x86-32 (`constant_time_impl.h:120-348`). For example, the x86-64 `mbedtls_ct_bool` does `neg` / `or` / `sar $63`, giving an all-ones or all-zeros mask with no flags-dependent branch.
- **Gating.** `MBEDTLS_CT_ASM` is defined only when `MBEDTLS_HAVE_ASM` is set, the compiler defines `__GNUC__` (or is ARMCC ≥ 6), and the architecture is one of the four above (`constant_time_impl.h:40-52`).
- **Memory operations.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers so the loop cannot exit early on the first difference. It also reduces the result to zero or non-zero without a branch (`constant_time.c:67-116`). `mbedtls_ct_memcpy_if` builds masks and copies both sources in full (`constant_time.c:169-212`).

**What happens on a compiler or target that cannot support it**

There is no compile-time error and no runtime warning. The code falls through to the `#else` branches, which are ordinary C that depends on the optimizer behaving:

- `mbedtls_ct_compiler_opaque` becomes `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a global `volatile` zero (`constant_time.c:23-30`). This is much slower and still relies on the compiler not hoisting the load.
- `mbedtls_ct_bool` and `mbedtls_ct_uint_lt` use arithmetic-mask C. The header states this was "observed to be constant-time" on gcc, clang and MSVC as of May 2023 (`constant_time_internal.h:55-59`, `constant_time_impl.h:127-128`). That is an observation, not a guarantee, and nothing in the build re-checks it on a new toolchain.

Cases that drop to the C path: `MBEDTLS_HAVE_ASM` undefined (it is a commented-out opt-out in `mbedtls_config.h:52`), MSVC/IAR/ARMCC-5, and any ISA outside Arm, AArch64, x86 and x86-64.

**How the claim is actually tested**

The only dynamic check is `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` and `_MEMSAN` (`mbedtls_config.h:2109-2142`). These are off by default. CI turns them on in `components-sanitizers.sh` and `components-configuration-crypto.sh` (`test_with_valgrind_constant_time` over `tests/suites/*constant_time*.data`). Those suites mark secrets with `TEST_CF_SECRET`/`TEST_CF_PUBLIC` from `framework/tests/include/test/constant_flow.h`. In this checkout the `framework/` directory is absent, so I could not read that header or run the valgrind suites. The gap is that the tests only fail if the secret-dependent behaviour shows up under valgrind or MSan in those particular configurations. A compiler that emits a branch on a path the tests do not exercise would pass.

**How far it reaches**

About 487 references to `mbedtls_ct_*` / `MBEDTLS_CT_*` across 29 library files. The heaviest users:

| Area | Files | Use |
|---|---|---|
| Bignum core and wrappers | `bignum_core.c`, `bignum.c`, `bignum_mod_raw.c` | `lt_ct`, `check_zero_ct`, `safe_cond_assign/swap`, GCD/modinv |
| RSA | `rsa.c` (40 refs) | PKCS#1 v1.5 and OAEP unpadding |
| Cipher / CBC padding | `cipher.c` (30 refs) | Padding removal without a padding oracle |
| TLS | `ssl_msg.c` (27), `ssl_tls12_server.c` (9) | Record padding check, premaster-secret decrypt-and-compare |
| PSA | `psa_crypto.c`, `psa_crypto_cipher.c`, `psa_crypto_mac.c` | Cipher finish and MAC tag comparison |
| Other | `cmac.c`, `ccm.c`, `gcm.c`, `chachapoly.c`, `nist_kw.c`, `base64.c` | Tag comparisons, KW padding, base64 decode |

Two indirect routes matter. `ecp.c` does not call `mbedtls_ct_*` directly, but its Montgomery-ladder swaps go through `mbedtls_mpi_safe_cond_assign/swap` (`ecp.c:1202-1215`), and those are built on `mbedtls_ct_bool`. Public API surface is limited to `mbedtls/constant_time.h` (`mbedtls_ct_memcmp`, `memcmp_partial`) and `mbedtls/bignum.h` (`mbedtls_mpi_lt_mpi_ct`).

Not covered: `aes.c`, `ecdsa.c`, `ecdh.c`, `md.c`, `hmac_drbg.c` and `psa_crypto_ecp.c` have no `mbedtls_ct_*` calls. Constant-time behaviour there depends on the arithmetic primitives they call and on the hardware AES paths. The facility does not make those paths constant-time by itself.

**Not verified:** I did not run the valgrind/MSan suites, so the tested-on-this-toolchain status is unknown. The `framework/` submodule is missing from this checkout, so the instrumentation header was not read.