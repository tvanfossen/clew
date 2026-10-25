## Short answer

Constant-time behaviour in mbedtls is a **convention enforced by code shape, not a guarantee the library checks**. The primitives are written so that a compiler has little reason to insert a branch. On GCC-compatible compilers on a few architectures, they are hand-written assembly that the compiler cannot rewrite. Nothing fails the build when that isn't available: the library falls back to plain C and carries on. The facility reaches roughly 30 library files, concentrated in RSA, bignum, CBC/MAC handling in TLS, and cipher code. Coverage is by call site, and I did not verify that every secret-dependent path goes through it.

## How it is enforced at the instruction level

The API is in `library/constant_time_internal.h` and `library/constant_time_impl.h`. Secrets are represented as `mbedtls_ct_condition_t`, which is an all-ones or all-zeros mask. Operations are bit arithmetic on masks, not `if` statements:

- **Mask generation** (`mbedtls_ct_bool`). The x86-64 asm is `mov; neg; or; sar $63`. That turns any non-zero input into all-ones and zero into all-zeros, with no branch and no conditional instruction. AArch64, ARM and x86 have matching asm.
- **Selection** (`mbedtls_ct_*_if`). Select between values with masks, for example `(a & m) | (b & ~m)`.
- **Opacity** (`mbedtls_ct_compiler_opaque`). This is the key defence. In the asm build it is `asm volatile("" : "+r"(x))`, a barrier that stops the optimizer from proving the value. In the C build it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global, so the compiler cannot know it is zero.
- **Memory operations** such as `mbedtls_ct_memcmp`, `mbedtls_ct_memcpy_if` and `mbedtls_ct_memcpy_offset` read every byte of every buffer regardless of the outcome. `mbedtls_ct_memcmp` casts its inputs to `volatile` so the compiler cannot add an early exit.

## What happens on a compiler that cannot support it

The asm path is gated in `constant_time_impl.h`:

```
MBEDTLS_HAVE_ASM && __GNUC__ (not old armcc)  ->  MBEDTLS_CT_ASM
   + arm/thumb  -> MBEDTLS_CT_ARM_ASM
   + aarch64    -> MBEDTLS_CT_AARCH64_ASM
   + x86_64     -> MBEDTLS_CT_X86_64_ASM
   + i386       -> MBEDTLS_CT_X86_ASM
otherwise       -> plain C fallback with volatile mbedtls_ct_zero
```

- **No compile-time error.** MSVC, IAR, a GCC-compatible compiler on an unlisted architecture, or a build with `MBEDTLS_HAVE_ASM` undefined all compile. The fallback is a plain C expression. Its header comment says it was "observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an observation, not a proof, and it is dated.
- **Silent degradation.** Nothing warns the integrator that they are on the fallback. The only way to know is to inspect the emitted assembly or check which macros the build defines.
- **Partial asm on unlisted GNU targets.** If `__GNUC__` is defined but the architecture is none of the four, `MBEDTLS_CT_ASM` is set, so the generic `asm volatile("")` barrier is used, but the mask code falls back to C.
- **Platform-specific carve-outs.** The `MBEDTLS_CT_SIZE_32` and `MBEDTLS_CT_SIZE_64` checks mean the asm only applies when the word size matches the mask type.

`SECURITY.md` (around lines 107–111) makes the policy explicit. Mbed TLS uses standard C, relies on known compilers, and says the timing countermeasures "may not be complete" given compiler and platform diversity. It asks integrators to build with `-O2` or `-Os`, and says the project treats exploitable timing side channels as vulnerabilities only under common compilers and optimization levels. `-O3`, `-Oz` and individual flags are not covered.

## How it is tested

- `tests/scripts/components-sanitizers.sh` (around line 95) runs `test_suite_constant_time` under Valgrind. By default this exercises the **plain C fallback**, and a separate step is labelled as testing the asm path.
- `tests/scripts/components-configuration-crypto.sh` (lines 21–35) runs the `*constant_time*.data` suites under Valgrind with `valgrind_cf`, and `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` / `_MEMSAN` are documented as opt-in extended checks.

The constant-flow checks are opt-in and only apply to the code paths the tests exercise. I did not confirm that every CI job enables them.

## How far it reaches

Counts of `mbedtls_ct_` references, from grep:

| Area | Files (refs) | Where it matters |
|---|---|---|
| RSA | `rsa.c` (37) | PKCS#1 v1.5 unpadding is done with masks and `ct_memmove_left`/`ct_zeroize_if` |
| Bignum | `bignum_core.c` (32), `bignum.c` (26), `bignum_mod_raw.c` (2) | Secret-dependent limb operations |
| Cipher and AEAD | `cipher.c` (30), `ccm.c`, `gcm.c`, `cmac.c`, `chachapoly.c` | Padding checks, tag comparison |
| TLS | `ssl_msg.c` (24), `ssl_tls12_server.c` (8), `ssl_tls13_server.c`, `ssl_tls.c`, `ssl_cookie.c` | CBC padding and MAC check (around lines 1798, 1916–1935), `mbedtls_ct_hmac` |
| PSA | `psa_crypto.c` (9), `psa_crypto_cipher.c`, `psa_crypto_mac.c`, `nist_kw.c` | Driver wrappers and key-wrap comparisons |
| Encoding | `base64.c` (21) | Constant-flow decode |

Limits:

- **Public API is tiny.** Only `mbedtls_ct_memcmp` is in `include/mbedtls/constant_time.h`. The rest is internal.
- **`ct_memmove_left` and `ct_zeroize_if`** exist only when `MBEDTLS_PKCS1_V15` and `MBEDTLS_RSA_C` are on.
- **Still dangerous.** The ChangeLog (around lines 10–18) says that after the recent fix for the PKCS#1 v1.5 timing oracle, RSA PKCS#1 v1.5 decryption "remains inherently dangerous" and should be avoided where possible.
- **Non-constant-time by design.** `mbedtls_ct_memcmp` is explicitly not constant-time in `n`, and `mbedtls_ct_memcpy_offset` depends on `offset_min`, `offset_max` and `len`.

## Gaps to check if this matters for your use

1. Build with `-O2` or `-Os` on GCC or Clang. Those are the flags the project tests and will treat as in scope.
2. On a platform outside the four asm targets, or with MSVC or IAR, you are running the C fallback. Inspect the disassembly of `mbedtls_ct_bool` and the critical paths before trusting it.
3. The library has the mask primitives, but I did not audit whether every secret-dependent branch in, say, bignum modular exponentiation goes through them.