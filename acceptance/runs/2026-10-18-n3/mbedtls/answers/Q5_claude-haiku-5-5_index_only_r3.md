The short answer: mbedtls enforces constant time by convention and by a small set of helpers, not by a compiler guarantee. The helpers use inline assembly where the compiler allows it and a volatile-based C fallback where it doesn't. Nothing fails to build on an unsupported compiler, so the fallback is silently weaker. The facility reaches the bignum, RSA, base64, and SSL record-MAC code. The SECURITY.md wording suggests the project treats the compiler as a residual risk.

**How it is enforced at the instruction level**

All the primitives live in `library/constant_time_impl.h`, with `library/constant_time.c` for the byte-buffer operations and `include/mbedtls/constant_time.h` as the public surface.

- **Masks instead of branches.** Conditions are a `mbedtls_ct_condition_t` that is either all-zeros or all-ones. `mbedtls_ct_bool(x)` turns any non-zero value into an all-ones mask with a few arithmetic ops (negate, OR, arithmetic shift). Comparisons such as `mbedtls_ct_uint_lt`, `_eq`, and `_ne` are built from that. Selection is done by masking, e.g. `mbedtls_ct_memcpy_if` computes `(src1 & mask) | (src2 & ~mask)`.
- **Hiding values from the optimizer.** `mbedtls_ct_compiler_opaque(x)` is the key trick. When `MBEDTLS_CT_ASM` is set, it is `asm volatile("" : [x] "+r"(x))`, which tells the compiler the value is opaque without emitting code. Otherwise it returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global set to 0. The point is that the compiler cannot prove the mask is 0 or all-ones, so it cannot turn the mask back into a branch or a conditional move.
- **Hand-written assembly per target.** `mbedtls_ct_bool` and `mbedtls_ct_uint_lt` have `asm volatile` bodies for AArch64, ARM (Thumb `negs/orrs/asrs`), and x86 and x86-64 (`neg/or/sar`). Each is selected by the `MBEDTLS_CT_*_ASM` macro and the word size (`MBEDTLS_CT_SIZE_32` / `_64`).
- **Volatile reads for buffers.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers and ORs the XOR differences into one accumulator, so there is no early exit. `mbedtls_ct_memcpy_offset` scans every possible offset in `[offset_min, offset_max]` and copies conditionally, so the access pattern depends only on the bounds, not the secret offset.
- **Verification.** The repo has `test_with_valgrind_constant_time` in `tests/scripts/components-configuration-crypto.sh`, which runs a dedicated set of constant-time tests under Valgrind.

**On a compiler that cannot support it**

- `MBEDTLS_CT_ASM` is defined only when `MBEDTLS_HAVE_ASM` is set and the compiler is GCC-compatible (`__GNUC__`) or ARM Compiler (`__ARMCC_VERSION`). Otherwise the asm bodies are compiled out.
- The C fallback still hides values with the volatile-zero XOR and keeps the mask arithmetic. The code comment says that in May 2023 trunk gcc, clang and MSVC did not turn it into branches. That is an observation about specific compiler versions, not a guarantee.
- I found no build-time error or warning when the asm path is unavailable. A compiler that is more aggressive than those tested can still reintroduce branches, and nothing in the build detects it.
- `SECURITY.md` ("Caveats") says Mbed TLS uses standard C except with known compilers, does not expect compilers to introduce direct vulnerabilities, and warns that compilers *can* introduce timing side channels in code meant to be constant-time. Exploitable timing channels seen with a common compiler are treated as vulnerabilities. I only got fragments of that section, so the exact wording on unsupported compilers may be more specific than what I can report.

**How far it reaches**

Callers I could confirm from the index:

| Area | Constant-time use |
|---|---|
| Bignum (`bignum_core.c`, `bignum.c`) | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_cond_assign` / `_cond_swap` (via `mbedtls_ct_mpi_uint_if`), `mbedtls_ct_mpi_sign_if`, `mbedtls_mpi_lt_mpi_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_gcd_modinv_odd` |
| RSA (`rsa.c`) | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` scans the whole buffer, uses `mbedtls_ct_zeroize_if` on failure, and is the Bleichenbacher padding-oracle defense |
| Base64 (`base64.c`) | `mbedtls_ct_base64_dec_value` and `mbedtls_ct_base64_enc_char` avoid table lookups indexed by secret data |
| TLS record layer (`ssl_msg.c`) | `mbedtls_ct_hmac` computes the MAC over a secret-length record in constant flow by cloning the hash context and finishing at each candidate length, which is the Lucky13 defense |
| Public API | `mbedtls_ct_memcmp` for MAC and tag comparison |

The index also has `mbedtls_ct_memcpy_if` and `mbedtls_ct_memcpy_offset` in `constant_time.c`, and `mbedtls_ct_uint_*` as the building blocks for the rest. `library/constant_time.c` shows `mbedtls_ct_memcmp` as `orphan`, meaning the index found no callers for it. That is probably because callers reach it through the public header, not because it is dead.

**Limits of the reach**

- The PSA side does not get an equivalent. `docs/psa-transition.md` says the PSA API has no counterpart to `constant_time.h`, and that MAC and hash comparisons should use `mbedtls_ct_memcmp` or an equivalent.
- `3rdparty/p256-m` has its own constant-time story. It uses Fermat inversion and treats `MUL64_IS_CONSTANT_TIME` as a platform assertion that the user has to set, so it does not rely on `constant_time.h`.
- `SECURITY.md` says it gives no guarantees against local non-timing side channels, and `docs/psa-transition.md` notes that a timing-safe comparison is still needed for MACs and hashes once code moves to PSA.

I could not check whether every secret-dependent path in the library uses these helpers. The index tracks callers, but it cannot show what was left out. Where the index shows a function with no constant-time helper, the gap is absence of evidence, not proof of a leak.