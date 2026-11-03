## Short answer

Constant-time behaviour in mbedtls is not checked by the compiler or the build. It rests on three things: hand-written assembly on four architectures that pins the instruction sequence, `volatile` and asm barriers that stop the optimiser from seeing through the values, and dynamic tests under Valgrind and MemorySanitizer. On any other compiler or architecture, the C fallback is only *observed* to be constant-time on the compilers checked in 2023. Nothing fails the build. The facility reaches the bignum, RSA, EC, TLS record and AEAD tag-check code, but not the block ciphers.

## How it is enforced at the instruction level

**1. Masks instead of branches.** Secret conditions are never `bool`. They are `mbedtls_ct_condition_t` values that are either all-zeros or all-ones (`constant_time_internal.h:65-86`). `mbedtls_ct_bool(x)` builds the mask with a `neg`/`orr`/`asr` sequence on AArch64, the equivalent on ARM and x86, or a portable sign-bit trick in C (`constant_time_impl.h:120-203`). Selection is `(c & a) | (~c & b)` (`mbedtls_ct_if`, `:205-269`). Comparisons such as `mbedtls_ct_uint_lt` (`:271-380`) are built from these.

**2. Barriers against the optimiser.** `mbedtls_ct_compiler_opaque()` (`constant_time_impl.h:85-93`) hides a value from the compiler:
- With asm available: `asm volatile("" : "+r"(x))`.
- Otherwise: `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a global `volatile` set to 0 (`constant_time.c:29`). The compiler cannot prove it is zero, so it cannot fold the branch away.

**3. Pinned asm.** On ARM (32-bit and Thumb), AArch64, x86 and x86-64, the mask and select primitives are written in `asm volatile` (`constant_time_impl.h:130-349`). The compiler therefore cannot turn them back into a conditional jump.

**4. Memory operations.** Block operations always touch the same bytes regardless of the secret:
- `mbedtls_ct_memcpy_if` reads both sources and writes `dest` every time, using masks (`constant_time.c:169-212`).
- `mbedtls_ct_memcmp` uses volatile reads and an XOR accumulator with no early exit (`constant_time.c:67-116`).
- `mbedtls_ct_memcmp_partial`, `mbedtls_ct_memmove_left`, `mbedtls_ct_zeroize_if` and `mbedtls_ct_memcpy_offset` follow the same pattern.

**5. What makes it a contract rather than a convention.** Almost nothing. `mbedtls_ct_condition_t` is a plain `uint32_t` or `uint64_t` typedef (`constant_time_internal.h:65-85`). The header says "must be treated as opaque", and every argument is "considered secret", but a stray `if (cond)` compiles without complaint.

**6. Dynamic verification.** Tests call `TEST_CF_SECRET()` on secret inputs, which marks them as undefined for Valgrind memcheck. Any branch or memory address that depends on them is then reported (`tests/suites/test_suite_cipher.function:901`, and others). The `test_with_valgrind_constant_time` helper runs the `*constant_time*.data` suites under memcheck (`tests/scripts/components-configuration-crypto.sh:25-33`). The gate is `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (`mbedtls_config.h:2126`). A MemorySanitizer variant also exists, and `check_config.h:250` refuses to build it with asm.

**Limits of that check:** it only covers tested inputs and paths. Valgrind catches secret-dependent control flow and addresses. It does not catch variable-latency arithmetic or cache effects. `mbedtls_ct_memcmp` is constant with respect to the data but not the length `n`, which the header says explicitly.

## What happens on a compiler that cannot support it

The asm path is selected in `constant_time_impl.h:40-52`. It requires `MBEDTLS_HAVE_ASM`, a GNU-compatible compiler (`__GNUC__`), and a recognised architecture. Otherwise the C fallback is compiled. That covers:
- MSVC, IAR, and armcc5 (explicitly excluded at line 40).
- Any architecture outside the four listed, such as RISC-V.
- Any build with `MBEDTLS_HAVE_ASM` undefined. `configs/config-symmetric-only.h` leaves it commented out.

There is no `#error`, no warning and no build-time check. `check_config.h` only checks the MemSan and `HAVE_INT64` interactions. The fallback is written to avoid branches, and its header says it "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an observation, not a guarantee, and it is the only support statement in the code.

CI covers the no-asm case with `component_release_test_valgrind_constant_flow_no_asm` (`tests/scripts/components-sanitizers.sh:105-129`). That runs the fallback under memcheck on the CI compiler (GCC), not on yours.

## How far the facility reaches

Counts are from `grep -c` for `_ct\b|_ct\(|mbedtls_ct_` across `library/`: 430 matching lines in 33 files. Those include test-vector names, so treat them as an upper bound.

| Area | Uses the facility? | Evidence |
|---|---|---|
| Bignum core | Yes | `bignum_core.c:169` `mbedtls_mpi_core_cond_assign`; `bignum.c:116` `mbedtls_mpi_safe_cond_assign` |
| ECC (ECP) | Partly | `ecp.c:1202-1215` and `:2143` use the safe conditional assign and swap. Comments at `:2734`, `:2769`, `:2873` say some paths are "NOT constant-time" |
| RSA | Yes | PKCS#1 v1.5 unpadding (`rsa.c:503`, `:519`); OAEP hash check (`:2049`); verify compares (`:2530`, `:2774`) |
| TLS record and handshake | Yes | `ssl_msg.c:147`, `:250` for padding; MAC compares at `:1798`, `:2071`; also in `ssl_tls12_*.c`, `ssl_tls13_*.c`, `ssl_cookie.c` |
| AEAD and MAC tag compares | Yes | `gcm.c:760`, `ccm.c:590`, `chachapoly.c:320`, `cipher.c:1298`, `:1319`, `psa_crypto_mac.c:445`, `nist_kw.c:358` |
| PSA | Partly | Hash and MAC compares in `psa_crypto.c:2514`, `:2584`, `:3013` |
| Base64 | Yes | `base64.c`, 21 lines |
| AES, Camellia, ARIA | **No** | Grep finds only test-vector names such as `aes_test_ctr_ct` |
| SHA family | **No** | No matches in `sha*.c` |

So the facility covers the secret-dependent *control flow* in the places that compare secrets or branch on secret lengths and padding. It does not cover the table-lookup cache behaviour of the block ciphers, and the code says so for ECP.

**Index discrepancy:** clew reports `mbedtls_ct_memcmp` as `liveness: orphan`, with its only caller being itself. Grep finds more than 15 call sites in `ccm.c`, `gcm.c`, `rsa.c`, `ssl_msg.c` and others. I trust the grep result. The index is probably not resolving calls made through the macro-wrapped `psa_crypto_driver_wrappers.h` and TLS paths.

I did not fully read the `cipher.c` padding code or the `base64.c` lookup code, so those rows rest on the call-site counts only.