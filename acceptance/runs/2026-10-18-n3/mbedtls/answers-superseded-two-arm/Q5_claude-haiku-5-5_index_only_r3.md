## Short answer

Constant-time behaviour in mbedtls is enforced by convention, not by the compiler. The library writes branch-free mask arithmetic, pins the mask computation in hand-written inline assembly on four specific ISAs, and uses an opaque barrier so the optimiser cannot see through the masks. Where the assembly is not available, it falls back to plain C that relies on the compiler not introducing branches. Nothing in the index shows a build error or warning in that fallback case, so it is silent. The facility is a shared primitive layer (`library/constant_time*.h`, `constant_time.c`) used by several secret-dependent paths. I could not establish from the index how complete that coverage is.

## How it is enforced at the instruction level

The core is a small set of primitives in `library/constant_time_impl.h`. Everything is built on an opaque condition type, a mask that is either all-zeros or all-ones.

| Primitive | Job | Enforcement |
|---|---|---|
| `mbedtls_ct_compiler_opaque` (`constant_time_impl.h:85`) | Hides a value from the optimiser | Asm path: `asm volatile("" : [x] "+r" (x) :)`, an empty asm that forces `x` through a register. Fallback: `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global (`constant_time.c:29`) |
| `mbedtls_ct_bool` (`:120`) | Turns a nonzero word into an all-ones mask | Hand-written `neg`/`orr`/`asr` (AArch64), `negs`/`orrs`/`asrs` (Thumb-2), `neg`/`or`/`sar` (x86-64 and x86-32). Fallback: arithmetic on the opaque value |
| `mbedtls_ct_if` (`:205`) | Constant-time select `cond ? if1 : if0` | Asm `and`/`not`/`and`/`or` sequences per ISA. Fallback: `(cond & if1) \| (~cond & if0)` |
| `mbedtls_ct_memcmp` (`constant_time.c:67`) | Constant-time buffer compare | Reads through `volatile` pointers so the compiler cannot exit early, ORs the XOR differences, and reduces to a non-negative `int` |

The asm variants are chosen by a `#if` chain. The architecture is picked by `MBEDTLS_CT_AARCH64_ASM` (`__aarch64__`), `MBEDTLS_CT_ARM_ASM` (`__arm__`/`__thumb__`), `MBEDTLS_CT_X86_64_ASM` (`__x86_64__`/`__amd64__`) or `MBEDTLS_CT_X86_ASM` (`__i386__`). Each is gated on `MBEDTLS_HAVE_ASM` and `__GNUC__` or `__ARMCC_VERSION`. The operand width comes from `MBEDTLS_CT_SIZE_32` or `MBEDTLS_CT_SIZE_64`.

The asm is what pins the instruction sequence. The empty `asm volatile` in `mbedtls_ct_compiler_opaque` is the optimisation barrier that stops the compiler from folding the masks back into a branch.

## What happens on a compiler that cannot support it

- **Asm unavailable** (non-GNU, non-ARMCC, or `MBEDTLS_HAVE_ASM` off, or an arch the `#if` chain does not match): the `#else` branches are used. Those are plain C mask expressions, with the opaque barrier still applied through the `^ mbedtls_ct_zero` trick.
- **What that buys you:** the source has no branch in it, but nothing forces the output to stay branch-free. The `mbedtls_ct_bool` comment says the C fallback "does not get optimised into conditional instructions or branches by trunk clang, gcc, or MSVC v19" as of May 2023. That is a dated statement about specific compilers, not a guarantee.
- **Failure mode:** the index shows no `#error` or warning for the fallback. The only hard `#error` I saw is in `mbedtls_ct_memcmp` for `int` narrower than 32 bits.
- **Documented caveat:** `SECURITY.md` says "compilers can introduce timing side channels in code that was intended to be constant-time" and that exploitable timing channels with a common compiler are treated as vulnerabilities. The text I could see is truncated, so I cannot confirm the full wording.

## How far it reaches

The primitives are used in a set of secret-dependent paths. The index shows these call sites:

| Location | Use |
|---|---|
| `library/rsa.c` `mbedtls_ct_rsaes_pkcs1_v15_unpadding` | PKCS#1 v1.5 unpadding. Its comment cites Bleichenbacher-style padding oracles |
| `library/ssl_msg.c` `mbedtls_ct_hmac` | TLS record MAC over a possibly padded record. Uses `psa_hash_clone()` to get constant-flow behaviour |
| `library/base64.c` `mbedtls_ct_base64_dec_value` | Base64 decoding with no table lookup or branch on the character |
| `library/bignum_core.c` `mbedtls_mpi_core_lt_ct`, `check_zero_ct` | Bignum comparison and zero test |
| `library/bignum.c` `mbedtls_ct_mpi_sign_if`, `library/bignum_internal.h` `mbedtls_mpi_gcd_modinv_odd` | Bignum sign select and odd-modulus inverse |
| `include/mbedtls/bignum.h` `mbedtls_mpi_lt_mpi_ct` | Public constant-time MPI comparison |
| `include/mbedtls/constant_time.h` `mbedtls_ct_memcmp` | Public buffer comparison |
| `3rdparty/p256-m` | Separate constant-time P-256 implementation. Its README says it is "fully constant-time from the ground up". It has its own `MUL64_IS_CONSTANT_TIME` switch |
| `docs/psa-transition.md`, `include/psa/crypto.h` `psa_aead_verify` | Docs require constant-time tag and MAC comparison |

Other facts from the index:

- `mbedtls_ct_if` also has a caller in `mbedtls_get_pkcs_padding` (AST-resolved).
- The test `test_with_valgrind_constant_time` in `tests/scripts/components-configuration-crypto.sh` runs a small set of dedicated constant-time tests under Valgrind. The index does not say how Valgrind is used to check secret-dependence.
- `CT_VALGRIND` and `CT_MEMSAN` appear as gate symbols in the repo, but I did not dig into what they control.

## What the index cannot settle

- **Coverage completeness.** The index cannot tell whether ECP scalar multiplication, AES, or other secret-dependent code paths use these primitives. Finding no caller does not prove they do not.
- **Callers of `mbedtls_ct_memcmp`.** The index marks it `orphan`, with 26 unresolved call sites, so the caller list is not reliable.
- **Gate logic.** I read the `MBEDTLS_CT_*_ASM` gate expressions as recorded `if_expr` gates on `MBEDTLS_HAVE_ASM`, `__GNUC__` and `__ARMCC_VERSION`. I did not verify the exact boolean.
- **Default configuration.** Gates such as `MBEDTLS_HAVE_ASM` come from several `configs/` files and `mbedtls_config.h`. The index has no recorded config header for this target, so I cannot say which of these is on by default.
- **Compiler-output correctness.** Nothing here verifies the emitted machine code, so this is a source-level claim plus the asm pins.