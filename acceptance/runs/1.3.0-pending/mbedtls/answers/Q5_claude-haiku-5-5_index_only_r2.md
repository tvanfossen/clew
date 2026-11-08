The constant-time guarantee is a coding discipline, not a checked property. Nothing in the index shows a build step that inspects the generated code, so it is enforced by how the primitives are written, plus a Valgrind test subset. The index only shows that test's name and brief, not its method.

**How it is kept at the instruction level**

The primitives live in `library/constant_time_impl.h`, with the public API in `include/mbedtls/constant_time.h` and the `.c` helpers in `library/constant_time.c`. They use four techniques:

- **Masks instead of branches.** `mbedtls_ct_bool(x)` returns all-ones if `x != 0` and zero otherwise. On x86-64 it is `mov; neg; or; sar $63`, so the sign bit of `-x | x` is smeared across the word. Comparisons such as `mbedtls_ct_uint_eq/ne/lt/ge` are built from it, and selection is done with `and`/`or` on masks.
- **Branch-free select.** `mbedtls_ct_memcpy_if` computes `dest = (src1 & mask) | (src2 & ~mask)`. It always reads `len` bytes from both sources, so the memory access pattern does not depend on the condition.
- **A compiler barrier.** `mbedtls_ct_compiler_opaque(x)` hides the value from the optimiser. With inline asm it is an empty `asm volatile` with `"+r"` on `x`. Otherwise it XORs with `mbedtls_ct_zero`, which is declared `volatile` in `constant_time.c`. Without the barrier, the compiler could prove the value and reintroduce a branch.
- **Volatile reads for comparisons.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers, ORs all the XOR differences together, and folds the result with no early exit. The header states it is constant with respect to the data but **not** with respect to `n`.

**What happens on a compiler that cannot support it**

Inline asm is selected by `MBEDTLS_CT_ASM`. Its gate in `constant_time_impl.h` (lines ~40–52) requires `MBEDTLS_HAVE_ASM` plus `__GNUC__` or `__ARMCC_VERSION`. The index lists `MBEDTLS_HAVE_ASM` as default-on at `include/mbedtls/mbedtls_config.h:52`, but it records no config header for this build, so the shipped default for the asm path is not confirmed.

When the gate is false, the code falls back to plain C. I found no `#error` or warning for that case. The only `#error` in the area is in `mbedtls_ct_memcmp`, and it fires when `int` is narrower than 32 bits. The fallback's branch-freeness rests on a comment that says that, as of May 2023, trunk clang, gcc and MSVC 19 did not turn these into branches. Nothing re-checks that on a new compiler, so the degradation is silent.

The asm variants cover only some architectures and word sizes:

| Path | Architecture | Word size |
|---|---|---|
| `MBEDTLS_CT_AARCH64_ASM` | AArch64 | 32 or 64 |
| `MBEDTLS_CT_ARM_ASM` | 32-bit ARM | 32 |
| `MBEDTLS_CT_X86_64_ASM` | x86-64 | 32 or 64 |
| `MBEDTLS_CT_X86_ASM` | x86 | 32 |

Anything outside that table uses the C fallback.

**How far it reaches**

The facility is a utility layer, and the index shows it used in these places:

- **Bignum:** `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, the public `mbedtls_mpi_lt_mpi_ct`, `mbedtls_ct_mpi_sign_if`, and `mbedtls_mpi_gcd_modinv_odd`, which wraps a constant-time GCD/inverse. The docs say the bignum routines are constant in value but not in limb count.
- **RSA PKCS#1 v1.5 decrypt:** `mbedtls_ct_rsaes_pkcs1_v15_unpadding` in `library/rsa.c`. Its comment names Bleichenbacher padding-oracle attacks, and it reads the whole buffer and tracks the padding in masks.
- **TLS record MAC:** `mbedtls_ct_hmac` in `library/ssl_msg.c`. It hashes to the minimum length, clones the hash context and finishes it at each candidate length, keeping only the correct result. This is the Lucky13-style fix for variable-length records.
- **Base64 decode:** `mbedtls_ct_base64_dec_value` decodes without a lookup table indexed by secret input.
- **PSA verify functions:** `psa_mac_verify_finish`, `psa_hash_verify`, `psa_aead_verify` and `psa_key_derivation_verify_bytes` carry a "best effort" constant-time obligation in their docs. This is an API requirement on implementations, not a separate mechanism.
- **p256-m** under `3rdparty/` is a separate ECC implementation. Its README says it is constant-time throughout, with a `MUL64_IS_CONSTANT_TIME` switch for platforms with a fast 32×32→64 multiply.

The facility stops at timing. `SECURITY.md` says Mbed TLS makes no guarantees against local attacks that are not timing-based. Its caveats section says compilers can introduce timing side channels into code meant to be constant-time, and the library does not claim to prevent that.

**Limits of this answer**

- The index has no disassembly, so I could not confirm that any compiler actually emits branch-free code for these functions.
- The Valgrind test is identified only by name and brief, so I cannot say what it checks.
- My caller search was capped at 80 symbols. It is not a full census of `mbedtls_ct_*` call sites. For example, the index marks the public `mbedtls_ct_memcmp` as `orphan`, meaning it found no in-library caller. That is consistent with a public API, but I did not confirm it.