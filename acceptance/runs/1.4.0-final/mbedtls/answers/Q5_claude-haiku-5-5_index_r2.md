**Short answer:** constant-time is enforced by convention, targeted assembly, and a test harness. Nothing checks the emitted machine code at build time. The guarantee is strongest on x86, 32-bit Arm and AArch64 with `MBEDTLS_HAVE_ASM`. Elsewhere it rests on the C compiler not turning masks into branches.

**1. How it is enforced at the instruction level**

The primitives live in `library/constant_time_impl.h` and are built on a few rules:

- **Secret values are masks, not booleans.** `mbedtls_ct_bool()` turns any non-zero value into all-ones or all-zeros (`constant_time_impl.h:120`). Everything else works on those masks: `mbedtls_ct_if()` (`:205`) selects with `and/or/not`, and comparisons such as `mbedtls_ct_uint_lt()` (`:271`) compute a sign bit with `sub`/`sar` and never branch.
- **Assembly where the arch is known.** When `MBEDTLS_HAVE_ASM` is set and the compiler is GCC-compatible (`constant_time_impl.h:40`), the code selects one of four blocks: `MBEDTLS_CT_ARM_ASM`, `MBEDTLS_CT_AARCH64_ASM`, `MBEDTLS_CT_X86_64_ASM` or `MBEDTLS_CT_X86_ASM`. Each has hand-written `neg/orr/asr`, `and/not/or`, or `sar` sequences, so no branch or conditional instruction is emitted. Some blocks are limited by width. The 32-bit x86 and Arm variants are only selected for `MBEDTLS_CT_SIZE_32`, so 64-bit `mbedtls_ct_uint_t` on a 32-bit CPU falls through to C.
- **`mbedtls_ct_compiler_opaque()` blocks value tracking.** It is an empty `asm volatile` barrier, or `x ^ mbedtls_ct_zero` where a volatile global holds zero (`:85`). This stops the optimizer from proving a secret's value and folding the mask logic away.
- **Memory traffic is fixed.** `mbedtls_ct_memcmp()` reads both buffers through `volatile` pointers and ORs the differences into `diff` with no early exit (`library/constant_time.c:67`). `mbedtls_ct_memcpy_if()` reads both sources and writes `dest` on every call, using mask-and-OR. `mbedtls_ct_memcpy_offset()` scans every possible offset from `offset_min` to `offset_max` (`:214`), so the access pattern depends on the bounds, not the secret offset.

**2. What happens on a compiler or CPU that cannot support it**

There is no `#error` and no warning. The code drops to the portable C branch, which uses the same mask arithmetic plus the `volatile` zero trick. The header comment says this C fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h:55`). That is an observation about compiler output on those versions, not a guarantee.

Concretely:

| Situation | Result |
|---|---|
| `MBEDTLS_HAVE_ASM` undefined | C fallback everywhere |
| MSVC or any non-GNU compiler | C fallback (`MBEDTLS_CT_ASM` needs `__GNUC__`) |
| Arch with no asm block (RISC-V, MIPS, etc.) | C fallback |
| 64-bit `mbedtls_ct_uint_t` on 32-bit Arm/x86 | C fallback for that op |

The one hard stop is the MemorySanitizer combination: `check_config.h:250` refuses `MBEDTLS_HAS_MEMSAN` with `MBEDTLS_HAVE_ASM`, because MSan cannot follow the asm. The flag is only a build-time check for the test build, so a user can build without it.

**3. How far the facility reaches**

- **Scale:** `mbedtls_ct_` is used 286 times across 29 files. About 100 of those are in the three `constant_time*` files; the rest are call sites.
- **Crypto with secret-dependent checks:** MAC and tag verification in `cipher.c`, `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c` and `psa_crypto_mac.c`. Padding and signature checks in `rsa.c` (PKCS#1 v1.5 verify and sign, OAEP decrypt). Key unwrap in `nist_kw.c`.
- **Bignum:** `bignum.c`, `bignum_core.c`, `bignum_mod_raw.c` and `base64.c` use the primitives for secret-value handling (roughly 20 uses each).
- **TLS:** record decryption MAC in `ssl_msg.c`, Finished checks in `ssl_tls.c` and `ssl_tls13_generic.c`, PSK binder and identity matching in the TLS 1.3 server, cookie checks, and renegotiation info.

What it does not reach: most of the library is not wrapped. Table-based AES, general bignum paths not listed above, and the ECC code in `3rdparty/p256-m` each have their own, separately documented side-channel notes. Nothing in the library enforces that a new secret-dependent branch goes through `mbedtls_ct_`. The `constant_time.h` doc says `mbedtls_ct_memcmp()` is "not constant-time w.r.t. `n`", so length still leaks.

**4. How it is tested**

Two opt-in test-only settings exist: `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` and `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` (`mbedtls_config.h:2126` and `:2109`). They mark secret inputs as undefined and let the test run under valgrind memcheck or clang MSan, so a secret-dependent branch or index shows up as an uninitialised-value report. CI runs these in `tests/scripts/components-sanitizers.sh`, including a build without `MBEDTLS_HAVE_ASM` so the C fallback is tested too. The dedicated suite is `tests/suites/test_suite_constant_time.function`. These are explicitly not part of the public API.

**Gaps I did not check:** I did not read the Arm, AArch64 or x86 asm sequences against the ISA manuals, and I did not confirm the MemSan poison helper definitions. The index shows the `mbedtls_ct_memcmp` caller list, but I did not verify every call site for leaks.