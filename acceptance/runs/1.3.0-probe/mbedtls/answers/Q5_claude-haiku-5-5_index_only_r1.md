**Short answer:** constant-time behaviour is a coding discipline backed by a small set of helpers, not something the compiler is forced to honour. The helpers use inline assembly on some targets and a volatile-barrier C fallback elsewhere. Nothing in the build fails when assembly is unavailable. The only check is a Valgrind/MemSan test mode that is off by default. The index cannot see generated machine code, so the instruction-level claims below come from the source, not from inspecting the binary.

**How it is enforced at the instruction level**

- **Helper layer.** `library/constant_time_impl.h` provides branch-free primitives: `mbedtls_ct_bool`, `mbedtls_ct_uint_lt`, `mbedtls_ct_uint_eq`, `mbedtls_ct_if`, `mbedtls_ct_bool_and/or/not`, and so on. Conditions are full-width masks (all ones or all zeros), not 0/1 values.
- **Assembly paths.** Each helper has hand-written `asm volatile` versions for specific targets: AArch64, 32-bit ARM (Thumb-aware), x86-64, and x86-32. Each is selected by an arch macro plus a size macro (`MBEDTLS_CT_SIZE_32` or `_64`). For example, `mbedtls_ct_bool` uses `neg / or / asr` on AArch64 and `mov / neg / or / sar` on x86-64.
- **Opacity barrier.** `mbedtls_ct_compiler_opaque` (`constant_time_impl.h:85`) stops the compiler from folding a value it could otherwise prove. With `MBEDTLS_CT_ASM` it is an empty `asm volatile` with a register constraint. Otherwise it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` zero defined in `library/constant_time.c:29`.
- **Comparison.** `mbedtls_ct_memcmp` (`constant_time.c:67`) reads both buffers through `volatile` pointers, accumulates XOR differences with no early exit, and reads all bytes even after a mismatch.

**What happens on a compiler that cannot support it**

- `MBEDTLS_CT_ASM` requires `MBEDTLS_HAVE_ASM` (on by default at `mbedtls_config.h:52`) and either `__GNUC__` or `__ARMCC_VERSION`. Anything else, MSVC for example, drops to the C fallback silently.
- The C fallback still uses the volatile barrier, but its only protection is the claim in the code comment that, as of May 2023, trunk clang, gcc and MSVC 19 do not turn the mask code into branches or conditional instructions. That is a snapshot about specific compiler versions, not a guarantee. The index has no `#error` gating the asm path itself. The one `#error` is in `mbedtls_ct_memcmp`, and it only rejects `int` narrower than 32 bits.
- `SECURITY.md` (Caveats) says so directly: compilers can introduce timing side channels into code meant to be constant-time, and Mbed TLS makes no guarantee against local non-timing attacks.

**How it is checked**

- `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` and `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` are both defaulted off (`mbedtls_config.h:2123` and `:2142`).
- `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25`) runs the `*constant_time*.data` suites under Valgrind. That is the only dynamic check the index shows. It is a control-flow and secret-dependent-branch check, not a timing measurement.

**How far it reaches**

Confirmed callers in the index:

| Area | Site | Constant-time use |
|---|---|---|
| Bignum core | `mbedtls_mpi_core_lt_ct` (`bignum_core.c:133`), `mbedtls_mpi_core_check_zero_ct` | Full-limb compare that never early-exits |
| Bignum | `mbedtls_ct_mpi_sign_if` (`bignum.c:48`), used by `mbedtls_mpi_exp_mod_optionally_safe`, `mbedtls_mpi_safe_cond_assign`, `mbedtls_mpi_safe_cond_swap` | Conditional sign handling |
| RSA | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` (`rsa.c:420`), called from `mbedtls_rsa_rsaes_pkcs1_v15_decrypt` | PKCS#1 v1.5 unpadding without a padding oracle |
| TLS record | `mbedtls_ct_hmac` (`ssl_msg.c:65`), gated on CBC-MAC suites | MAC over variable-length, padded records |
| Base64 | `mbedtls_ct_base64_dec_value` (`base64.c:40`), `mbedtls_ct_base64_enc_char` | Table-free decode and encode |

The index flags `mbedtls_ct_memcmp` as *orphan* (no callers). That is probably wrong: its own report lists 26 unresolved call sites, so the flag cannot be trusted. It is the public API in `include/mbedtls/constant_time.h`.

The PSA docs state the requirement at the API level: `psa_aead_verify` must make a best-effort constant-time tag comparison, and `docs/psa-transition.md` says MAC checks should use the `mbedtls_ct_` helpers. Those are expectations on implementers, not proof that every path is covered.

**Limits of this answer:** the index gives no generated assembly, no timing measurements, and no record of which asm variants a release build actually selects. Verifying the instruction-level claims would need disassembly of a real build, and verifying coverage would need a review of every secret-dependent branch outside the callers listed above.