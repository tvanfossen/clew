**Short answer:** constant-time behaviour is enforced by coding discipline, not by a compiler guarantee. The library uses a small set of branch-free primitives (masks built with inline asm where available, plain C otherwise), and a few hot spots are checked with Valgrind. On a compiler without the asm path, the C fallback still runs but makes no hard guarantee, and the library's own SECURITY.md says so. The facility reaches the bignum, RSA, TLS record and base64 code, but not the whole library.

**How it is enforced at the instruction level**

- **Secret conditions are opaque masks.** `mbedtls_ct_condition_t` is a full-width mask, either all ones or all zeros (`MBEDTLS_CT_TRUE`/`MBEDTLS_CT_FALSE`, `library/constant_time_internal.h:70`). Comparisons and selects are arithmetic over these masks: `mbedtls_ct_uint_lt`, `mbedtls_ct_bool`, `mbedtls_ct_if` (`library/constant_time_impl.h`).
- **Hiding values from the optimiser.** `mbedtls_ct_compiler_opaque()` (`library/constant_time_impl.h:85`) is the key trick. With asm it is an empty `asm volatile` that pins the register value, so the compiler cannot prove what it is. Without asm it returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global holding 0 (`library/constant_time.c:29`), so the compiler cannot fold it away.
- **Per-architecture asm.** `mbedtls_ct_bool`, `mbedtls_ct_uint_lt` and `mbedtls_ct_if` have hand-written sequences for AArch64, 32-bit ARM, x86-64 and x86 (e.g. AArch64 `neg/orr/asr` for the nonzero mask).
- **Data-independent memory reads.** `mbedtls_ct_memcmp` (`library/constant_time.c:67`) accumulates XOR differences over `volatile` pointers, so the compiler must read every byte and cannot exit early. `mbedtls_ct_memcpy_if` does a masked copy that always reads both sources.
- **Testing.** `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25`) runs the `*constant_time*.data` suites under Valgrind. The PSA docs describe that as "Valgrind memory poisoning … for constant-flow testing" (`docs/architecture/psa-shared-memory.md`). The index shows the script, not the Valgrind mechanism itself, so I'm inferring the poisoning approach from that doc.

**What happens on a compiler that cannot support it**

- `MBEDTLS_CT_ASM` is defined only when `MBEDTLS_HAVE_ASM` is set and the compiler is GCC-like or ARMCC (`library/constant_time_impl.h:40-52`). Otherwise every asm branch is skipped and the plain-C versions are used.
- I found no `#error` or build-time refusal for this case. The only `#error` in this area is for `int` narrower than 32 bits, in `mbedtls_ct_memcmp`.
- The C fallback comments claim that, as of May 2023, trunk clang, gcc and MSVC do not turn it into branches. That is a claim about specific compiler versions, not a guarantee.
- SECURITY.md says that compilers can introduce timing side channels into code meant to be constant-time. It says Mbed TLS "includes countermeasures", but that given "the diversity of compilers, compiler options and target platforms" it cannot promise more. It also says there are no guarantees against local non-timing side channels.

**How far it reaches**

| Area | Constant-time code | Notes |
|---|---|---|
| Bignum core | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_lt_mpi_ct`, `mbedtls_ct_mpi_uint_if` | `mbedtls_mpi_core_lt_ct` scans every limb, latching the result with masks. |
| Modular inverse | `mbedtls_mpi_gcd_modinv_odd` | Wraps a constant-time GCD/inverse for odd moduli. |
| RSA PKCS#1 v1.5 | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` (`library/rsa.c:420`) | Explicitly written against Bleichenbacher padding-oracle timing. |
| TLS record MAC | `mbedtls_ct_hmac` (`library/ssl_msg.c:65`) | Hashes to the minimum length, then clones and finishes for each candidate length, to avoid length-dependent timing. |
| TLS decrypt | `mbedtls_ssl_decrypt_buf` | Uses `MBEDTLS_CT_TRUE` and the above helpers. |
| Base64 | `mbedtls_ct_base64_enc_char`, `mbedtls_ct_base64_dec_value` | |
| Comparisons | `mbedtls_ct_memcmp`, `mbedtls_ct_memcmp_partial` | |
| Bundled P-256 | `3rdparty/p256-m` | Described as fully constant-time; it also has a `MUL64_IS_CONSTANT_TIME` gate for platforms with a constant-time 32×32→64 multiply. |

Outside these areas, the index does not show a general mandate. Two limits apply:

- `mbedtls_ct_memcmp` is constant with respect to the data but not to `n`, so callers must not let the length be secret.
- The PSA API has no equivalent of these utilities (`docs/psa-transition.md`). PSA only asks implementations to "make the best effort" on tag comparison in `psa_aead_verify`. Constant-time behaviour in the PSA layer depends on the internal helpers being used.

**Limits of this answer**

- The index does not show every caller of `mbedtls_ct_memcmp` (26 are unresolved), so the reach list above is not exhaustive.
- The index has no `.clew.yaml`/config header for this repo, so I could not confirm which defaults are on in a shipped build.
- I did not read the full SECURITY.md caveat text; the quotes above are from search snippets.