## Enforcement at the instruction level

mbedtls's constant-time facility (`library/constant_time_internal.h` + `constant_time_impl.h`, backing `include/mbedtls/constant_time.h`) is built around an opaque type, `mbedtls_ct_condition_t`, that must never be produced by a branch. The primitives that create and combine it (`mbedtls_ct_bool`, `mbedtls_ct_if`, `mbedtls_ct_uint_lt`, ...) are `static inline`, and for the four architectures the library actually cares about — Arm 32-bit/Thumb, AArch64, x86, x86-64 — they're written as literal inline **GNU assembly**, gated behind `MBEDTLS_CT_ASM` and the per-arch `MBEDTLS_CT_ARM_ASM` / `MBEDTLS_CT_AARCH64_ASM` / `MBEDTLS_CT_X86_ASM` / `MBEDTLS_CT_X86_64_ASM` macros (`library/constant_time_impl.h:40-52`).

Concretely, e.g. `mbedtls_ct_bool` on x86-64 is `mov/neg/or/sar` with no comparison or jump instruction; `mbedtls_ct_if` (the constant-time select) is `and/not/and/or` — a bitmask blend, never a `cmov` or branch. This is deliberate: the comment block explicitly distrusts even `cmov`/conditional-select codegen, because a compiler is free to lower a C ternary into either a branch *or* a data-dependent instruction depending on optimization level, target, and version — so mbedtls pins the actual opcodes by hand rather than trusting the compiler's choice. `mbedtls_ct_compiler_opaque()` (an `asm volatile ("" : [x] "+r" (x) :)`) is the second half of the trick: an empty asm block with an inout constraint that forces the value through a register and blocks constant propagation/CSE, so the compiler can't fold the "secret" operand back down to a compile-time constant and reintroduce a branch anyway.

## What happens on a compiler/arch that can't do the asm

If `MBEDTLS_HAVE_ASM` isn't set, or `__GNUC__`-style extended asm isn't supported (MSVC, some other architecture, armcc5 in `--gnu` mode which defines `__GNUC__` but doesn't support GNU asm), `MBEDTLS_CT_ASM` is never defined and every primitive falls to a **plain C fallback** — bit-twiddling with masks (`(-x) | -(x>>1)`, shift-and-mask select, etc.) instead of asm. It is *not* a silent guess: the header states this fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" — i.e. it's an empirically-checked property of specific compiler versions, not a language guarantee, and the fallback still runs `mbedtls_ct_compiler_opaque()` (there implemented as `x ^ mbedtls_ct_zero`, XOR against a `volatile` global forced to be unknowable) to suppress the same optimizer folding the asm path prevents directly. So: no hard compiler enforcement exists on unsupported targets — it degrades to "best-effort C that has been checked not to get branch-optimized by the three tested compilers," with no runtime check that this held for whatever compiler was actually used to build.

## Reach into the rest of the library

The facility is not confined to one hot path; it's grep-visible across most of the secret-dependent logic:

| Consumer | approx. call sites | why |
|---|---|---|
| `bignum_core.c` / `bignum.c` / `bignum_mod_raw.c` | ~32+ | modular exponentiation / comparison on secret big integers (RSA/ECC math) |
| `rsa.c` | ~37 | PKCS#1 v1.5 padding checks, RSA-CRT, blinding — classic timing-oracle history |
| `cipher.c` | ~30 | padding removal (CBC padding-oracle defense) |
| `ssl_msg.c` (TLS 1.2/1.3 record layer) | ~24 | MAC/padding checks during record decryption |
| `gcm.c`, `chachapoly.c`, `ccm.c`, `cmac.c` | small counts | tag comparison |
| `nist_kw.c` | uses `mbedtls_ct_memcmp_partial` | key-wrap integrity check ignoring padding bytes |
| `psa_crypto.c`, `psa_crypto_cipher.c`, `psa_crypto_mac.c` | present | PSA-layer wrappers over the same primitives |
| `base64.c` | present | avoids leaking plaintext structure through decode branching |
| `ssl_tls.c`, `ssl_tls12_client/server.c`, `ssl_tls13_generic/server.c`, `ssl_cookie.c` | present | handshake-secret comparisons, cookie checks |

Beyond the scalar boolean/select ops, `constant_time.c` provides block-level primitives built on top: `mbedtls_ct_memcmp` (branchless buffer compare via `volatile`-qualified pointers to force full reads — the comment explains this specifically prevents the compiler early-exiting once `diff` has all bits set), `mbedtls_ct_memcpy_if`/`mbedtls_ct_memcpy_offset` (mask-blended conditional copy, including copying from a secret offset without branching on the offset), `mbedtls_ct_zeroize_if`, and `mbedtls_ct_memmove_left` (constant-time buffer shift used specifically in RSA PKCS#1 v1.5 unpadding). So the facility spans everything from a single secret-integer comparison up through whole-buffer padding/MAC checks in TLS record processing — it's the load-bearing timing-side-channel defense for the RSA, bignum/ECC, symmetric-cipher padding, AEAD tag verification, and TLS record-layer code, not a one-off utility.
