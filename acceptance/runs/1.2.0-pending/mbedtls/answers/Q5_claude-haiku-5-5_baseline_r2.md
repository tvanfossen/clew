**Short answer:** mbedtls does not enforce constant time at the instruction level. It hand-writes a few primitives in assembly for specific architectures, uses volatile and masking tricks elsewhere, and then checks the compiled output dynamically under Valgrind and MemorySanitizer. On a compiler without the assembly path it silently falls back to portable C, with no build error or warning. Its own SECURITY.md says the protection is "limited."

**1. How it is enforced**

- **Opaque conditions.** `mbedtls_ct_condition_t` is an all-ones or all-zeros mask, typed as a plain integer (`library/constant_time_internal.h:65-86`). Nothing stops `if (cond)` from compiling, so the rule "treat it as opaque" is convention plus review.
- **Hiding values from the optimizer.** `mbedtls_ct_compiler_opaque()` is an empty `asm volatile("" : "+r"(x))` when GNU asm is available (`library/constant_time_impl.h:85-93`). Otherwise it XORs with a `volatile` zero global (`library/constant_time.c:29`), so the compiler cannot prove a value at compile time and cannot turn masks back into branches.
- **Pinned instruction sequences.** `bool`, `if`, and `uint_lt` have hand-written asm for specific arch and word-size pairs. The `neg/orr/asr` mask, `and/not/and/or` select, and `sub/xor/and` compare sequences contain no `jcc` or `cmov` (`constant_time_impl.h:120-380`).
- **Byte-level primitives.** `mbedtls_ct_memcmp` reads through `volatile` pointers and accumulates XOR differences (`constant_time.c:67-116`). `mbedtls_ct_memcpy_if` uses mask-and-or on every byte (`constant_time.c:169-212`).

Asm coverage is narrower than the `MBEDTLS_CT_ASM` gate suggests:

| Target | `bool` / `if` / `lt` asm | Notes |
|---|---|---|
| AArch64 | yes, for 32- and 64-bit condition types | `impl.h:130,209,273` |
| x86-64 | yes, for 32- and 64-bit | `impl.h:157,238,314` |
| 32-bit Arm / Thumb | only when the condition type is 32-bit | `impl.h:142,222,289` |
| i386 | only when the condition type is 32-bit | `impl.h:170,251,332` |
| Other GNU-asm targets | none; C fallback, but `compiler_opaque` still uses asm | |

**2. A compiler that cannot support it**

- `MBEDTLS_CT_ASM` is defined only when `MBEDTLS_HAVE_ASM` is set and `__GNUC__` is present. Clang qualifies. MSVC, IAR, and armcc5 do not (`constant_time_impl.h:39-52`).
- Without it, the code uses the `volatile` zero trick and the C mask formulas. The header says this "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h:55-59`). That is an observation, not a guarantee.
- The only hard `#error` in this area guards `int` narrower than 32 bits, because `memcmp` depends on it (`constant_time.c:99-105`).
- MemorySanitizer builds reject asm outright (`check_config.h:250`). So the MSan path always runs the C fallback.

**3. Where the facility reaches**

The `mbedtls_ct_` API is used across roughly 25 library files. Counts below are occurrences, not distinct functions:

- **TLS record layer.** `ssl_msg.c` (24) has constant-time HMAC over the record, MAC comparison, and CBC padding checks (`ssl_msg.c:66,1916-1978,2044-2071`).
- **RSA.** `rsa.c` (37) has PKCS#1 v1.5 unpadding with error masking and `mbedtls_ct_zeroize_if` (`rsa.c:420-520`), plus constant-time signature and encoding comparisons (`rsa.c:2530,2774`).
- **Bignum.** `bignum_core.c` (32) has `mbedtls_mpi_core_lt_ct` and related comparisons. `bignum.c` (26) and `bignum_mod_raw.c` also use it.
- **Other.** `cipher.c` (30) for CBC padding, `base64.c` (21), `nist_kw.c` (4), `psa_crypto.c` (9), and tag comparisons in `gcm.c`, `ccm.c`, `cmac.c`, and `chachapoly.c`.

The limits are stated in `SECURITY.md`:
- Protection is only against "publicly documented attack techniques", and the library is "not reached" fully timing-invariant.
- Block ciphers are explicitly not fully protected.
- Physical, fault-injection, and local non-timing side channels are out of scope.
- The compiler should be run at `-O2` or `-Os`, and the document warns that other options may reintroduce data-dependent timing.
- Lengths are public. `mbedtls_ct_memcmp` is not constant-time in `n`, and `mbedtls_ct_memcpy_offset` leaks `offset_min` and `offset_max`.

**4. How the enforcement is checked**

- Suites annotated with `TEST_CF_SECRET` and `TEST_CF_PUBLIC` are run under Valgrind (`MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`) or MSan. Any branch or address that depends on a marked secret shows up as an uninitialized-value error (`tests/scripts/components-sanitizers.sh:12-21,115-135`).
- Eight suites carry annotations: cipher, constant_time, constant_time_hmac, bignum_core, bignum_mod_raw, pkcs1_v15, base64, and psa_crypto_constant_time. All other suites are skipped in those components.
- One Valgrind component keeps asm on, and another turns it off, so both paths get tested.

Two gaps follow from this. The check is dynamic, so it covers only the inputs and paths the tests execute. And the annotation harness (`framework/tests/include/test/constant_flow.h`) lives in a git submodule that is empty in this checkout, so I could not read the macros themselves.

**Not verified:** I did not inspect the AES table or modular-exponentiation paths. The statements about them come from SECURITY.md, and the reach figures are line counts from grep.