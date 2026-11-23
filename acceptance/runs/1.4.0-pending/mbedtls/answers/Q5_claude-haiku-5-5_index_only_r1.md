**Short answer:** constant-time behaviour in mbedtls is achieved by construction in a small helper layer, not enforced at the instruction level by a checker. An unsupported compiler silently gets the plain-C fallback, not a build error. The helpers are used widely across bignum, RSA, cipher padding, AEAD tag checks and TLS, but the index does not show a machine-checked guarantee for all of them.

**How it's enforced at the instruction level**

- The primitives live in `library/constant_time_impl.h`, with the public surface in `include/mbedtls/constant_time.h` (`mbedtls_ct_memcmp`) and internal types in `library/constant_time_internal.h`.
- Secrets are carried as a `mbedtls_ct_condition_t` mask, all-ones or zero, and combined with `mbedtls_ct_bool*`, `mbedtls_ct_uint_*`, `mbedtls_ct_if`, `mbedtls_ct_memcpy_if` and similar, so that no branch is taken on a secret value.
- `mbedtls_ct_bool(x)` is the mask generator. Where an assembly path is selected, it is hand-written: AArch64 (`neg`/`orr`/`asr`), 32-bit ARM (`negs`/`orrs`/`asrs`), x86-64 and x86 (`neg`/`or`/`sar`). Otherwise it uses a C fallback: `-x | -(x>>1)` and a shift to reduce the sign bit to a 0/1 mask.
- `mbedtls_ct_compiler_opaque(x)` is the anti-optimisation barrier. With `MBEDTLS_CT_ASM` it is an empty `asm volatile` taking `x` as an in/out register. Otherwise it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a variable the compiler cannot see the value of. Its job is to stop the compiler proving a value and turning the mask arithmetic back into a branch.
- `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers, XORs and ORs the differences, and returns a value that is non-zero iff the buffers differ. The `volatile` cast is there so the compiler cannot exit early on the first difference.

**What happens on a compiler that can't support it**

- The asm path is gated by `MBEDTLS_CT_ASM`, which is defined only when `MBEDTLS_HAVE_ASM` is on and `__GNUC__` or `__ARMCC_VERSION` is defined. On MSVC, or on any compiler outside that set, the code drops to the C fallbacks. This is a silent downgrade: there is no `#error` and no configuration check.
- The only hard `#error` in this path guards a different hazard: `mbedtls_ct_memcmp` refuses to build where `int` is narrower than 32 bits, because the final cast would lose the non-zero result.
- The C fallback's comment says that, as of May 2023, trunk clang, gcc and MSVC v19 do not turn it into branches. That is a dated observation about current compilers, not a guarantee.
- `SECURITY.md` ("Caveats") says in terms that compilers can introduce timing side channels into code meant to be constant-time, so the residual risk is acknowledged in the project's own documentation.

**How the guarantee is checked**

- There is no static analyser or instruction-level check in the index. Verification is dynamic: `test_with_valgrind_constant_time` in `tests/scripts/components-configuration-crypto.sh` runs `tests/suites/*constant_time*.data` under Valgrind in a `valgrind_cf` configuration. `components-sanitizers.sh` has a `component_release_test_valgrind_constant_flow` that runs only the constant_time suites under Valgrind or MemSan.
- I could not see from the index how secret data is marked for those runs. I also did not verify whether any test measures actual timing.

**How far it reaches**

The helpers are included by a large set of modules, and the index shows real call sites:

| Area | Where it's used |
|---|---|
| Bignum | `bignum_core.c` (`mbedtls_mpi_core_lt_ct`, conditional assign/swap, `montmul`, `gcd_modinv_odd`, zero check), `bignum.c`, `bignum_mod.c`, `bignum_mod_raw.c` |
| RSA | PKCS#1 v1.5 unpadding (`mbedtls_ct_rsaes_pkcs1_v15_unpadding`), OAEP decrypt, PKCS#1 v1.5 sign and verify comparisons |
| Block cipher padding | `cipher.c` padding removal, and `psa_crypto_cipher.c` |
| MAC and AEAD tag checks | `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `nist_kw.c`, `psa_crypto_mac.c`, PSA hash/MAC verify |
| TLS | `mbedtls_ct_hmac` in `ssl_msg.c` (constant-flow CBC MAC check), Finished and cookie checks, TLS 1.2 `ssl_parse_encrypted_pms`, TLS 1.3 PSK binder/identity matching |
| Other | `base64.c`, `ecp_curves.c`, `pk_wrap.c` |

Caveats on reach:

- The index does not show whether ECC scalar multiplication in `ecp.c` uses these helpers. `ecp_curves.c` includes them, but I did not check the point-multiplication path, so I cannot confirm coverage there.
- The P-256 code under `3rdparty/p256-m` is separate. It has its own constant-time design, with a `MUL64_IS_CONSTANT_TIME` switch and its own Valgrind/MemSan checks.
- Non-secret paths deliberately use ordinary branches. The `mbedtls_ct_memcmp` doc states it is not constant-time with respect to `n`, so the length is public.