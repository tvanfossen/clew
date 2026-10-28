## Short answer

Nothing enforces constant-time at the instruction level. The library *encourages* it. Hand-written inline asm pins the mask operations on four architectures, and a `volatile` trick stops the optimizer from reasoning about values. The actual check is done by tests running under Valgrind and MSan that flag any branch on secret data. On a compiler without asm support, the code silently falls back to plain C that is only observed to be constant-time, and the repository's own SECURITY.md says it is not guaranteed.

## How it is built

The primitives live in `library/constant_time_impl.h` and `library/constant_time_internal.h`, and the public surface is only `mbedtls_ct_memcmp` in `include/mbedtls/constant_time.h`. Everything else is internal.

- **Value type.** `mbedtls_ct_condition_t` is an unsigned word that is all-ones for true and all-zeros for false. It is sized to the pointer width or to 64 bits when 64-bit MPIs are enabled (`constant_time_internal.h:65-85`).
- **Mask generation.** `mbedtls_ct_bool(x)` turns "x != 0" into a mask with no branch. On x86-64 it is `mov / neg / or / sar $63` (`constant_time_impl.h:157-169`). The other mask and select operations (`mbedtls_ct_if`, the comparisons, `memcpy_if`) are built on the same mask arithmetic.
- **Opaque values.** `mbedtls_ct_compiler_opaque(x)` is `asm volatile("" : "+r"(x))` when asm is available. Otherwise it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global (`constant_time_impl.h:85-93`, `constant_time.c:29`). Its job is to stop the compiler from proving that a condition is `0` or `1` and turning it back into a branch.
- **Memory operations.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers so the loop cannot exit early on the first difference (`constant_time.c:67-116`). `memcpy_if` always reads both sources and always writes, with the selection done by masks.

## What gates the asm

Asm is used only when all of these hold (`constant_time_impl.h:40-52`):

- `MBEDTLS_HAVE_ASM` is defined. It is on by default and can be turned off by commenting it out (`mbedtls_config.h:32-52`).
- The compiler defines `__GNUC__`, and it is not armcc5. Clang qualifies. MSVC does not.

The per-architecture branch then selects `MBEDTLS_CT_ARM_ASM`, `MBEDTLS_CT_AARCH64_ASM`, `MBEDTLS_CT_X86_64_ASM` or `MBEDTLS_CT_X86_ASM`. Each operation also checks the word size, so there are gaps:

- On 32-bit Arm with 64-bit MPIs, `ct_uint_t` is 64 bits. The Arm asm requires `MBEDTLS_CT_SIZE_32`, so those operations drop to C.
- On other GNU-compatible targets, `MBEDTLS_CT_ASM` is defined but no architecture branch matches. `mbedtls_ct_compiler_opaque` still uses the generic `"+r"` asm, but each operation falls through to its C version.

## What happens on a compiler that cannot support it

It does not fail the build. Each operation has a `#else` C fallback, and `mbedtls_ct_zero` replaces the asm opaque barrier. The header says the fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h:55-59`). That is an observation, not a guarantee. The C fallback is also a volatile load on every opaque call, which is slower.

## How it is checked

There is no compile-time or link-time check that the emitted code is branch-free. Verification is dynamic:

- The test suites use `TEST_CF_SECRET` and `TEST_CF_PUBLIC` markers (`tests/suites/test_suite_constant_time.function`), which mark memory as undefined under Valgrind or MSan. A secret-dependent branch or memory index is then reported as an error.
- `test_with_valgrind_constant_time` runs `tests/suites/*constant_time*.data` under Valgrind, excluding the HMAC data (`components-configuration-crypto.sh:25-33`). It runs from the valgrind component at line 69 and the valgrind_cf component at line 3019.
- `components-sanitizers.sh:115-127` builds with `MBEDTLS_HAVE_ASM` unset and runs the constant-flow suites. That is the only CI path I found that exercises the C fallback under the checker.

So the fallback is tested, but only in one configuration.

## How far it reaches

Using `mbedtls_ct_*` calls as the measure, about 286 call occurrences across 29 library files:

| Area | Files (call occurrences) |
|---|---|
| Padding and MAC checks in TLS record handling | `ssl_msg.c` (22), `ssl_tls12_server.c` (7), `ssl_tls12_client.c`, `ssl_tls.c` |
| RSA PKCS#1 v1.5 handling | `rsa.c` (29) |
| Block cipher padding and CBC | `cipher.c` (25) |
| Bignum core and modular arithmetic | `bignum_core.c` (22), `bignum.c` (21), `bignum_mod_raw.c` (2), `bignum_mod.c` |
| Base64 | `base64.c` (21) |
| PSA and key wrap | `psa_crypto.c` (7), `psa_crypto_cipher.c`, `nist_kw.c` (4) |

`ecp.c` has no `mbedtls_ct_*` calls. Its constant-time claims rest on other techniques, such as reading the whole precomputed table and a constant-time comb recode (`ecp.c:2020, 2108`). Some of its functions are explicitly marked "NOT constant-time" (`ecp.c:2734, 2769, 2873`). The index shows `mbedtls_mpi_core_lt_ct` and `mbedtls_mpi_core_check_zero_ct` in `bignum_core.h`, which are the bignum-side equivalents.

Outside the facility:

- **p256-m** (`3rdparty/p256-m`) is self-contained. It uses its own `CT_POISON` Valgrind macro, and its multiplier choice depends on `MUL64_IS_CONSTANT_TIME` (`p256-m.c:44`).
- **Everest X25519** is HACL* and only guarantees protection against remote timing (`SECURITY.md`).
- **AES, Camellia, ARIA and DES** software implementations use lookup tables and are documented as vulnerable to timing attacks. The only workaround is hardware acceleration or a different primitive (`SECURITY.md`, "Block ciphers").

SECURITY.md's threat model says Mbed TLS "is moving towards a model of fully timing-invariant code, but has not reached this point yet". It also says compiler-introduced side channels are only mitigated, and that `-O2` / `-Os` are the levels it commits to.

## What I did not check

I did not run the test suites or any Valgrind or MSan build, so the claims about what they catch come from reading them. I did not read `tests/include/test/constant_flow.h`, which defines `TEST_CF_SECRET`. I did not check whether any CI component runs the constant-time suites under a non-GCC compiler, or on Arm 32-bit with 64-bit MPIs, which is the gap noted above.