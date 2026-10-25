**Short answer:** nothing in the build checks constant time. It is enforced by construction: secret values are only ever combined with bitwise masks, and a small set of hand-written assembly routines stops the compiler from turning those operations back into branches. Where that assembly isn't available, the code falls back to plain C that is only *observed* to be constant-time, and the build does not warn about it.

## How it is enforced at the instruction level

**Opaque conditions.** `mbedtls_ct_condition_t` is an unsigned integer that is always all-ones (true) or all-zeros (false). The header says it must be treated as opaque. Every boolean op (`mbedtls_ct_uint_eq`, `_lt`, `_bool_and`, …) produces one, and every select (`mbedtls_ct_uint_if`, `_if_else_0`, …) consumes one. Secret values never reach `if`, `?:` or `==` in library code.

**Hiding values from the optimiser.** `mbedtls_ct_compiler_opaque()` (`library/constant_time_impl.h:85`) is an empty `asm volatile("" : [x] "+r"(x))` on GCC-compatible builds. The compiler must assume the asm reads and writes `x`, so it cannot prove the value and fold a mask away. The C fallback instead does `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` zero defined in `library/constant_time.c:29`.

**Masks in assembly.** Four architectures get hand-written asm: AArch64, 32-bit ARM/Thumb, x86-64 and x86-32. These are gated on `MBEDTLS_HAVE_ASM` plus `__GNUC__`, which means clang qualifies. Examples:
- `mbedtls_ct_bool(x)` on x86-64 is `mov; neg; or; sar $63`. The sign bit of `x | -x` is set exactly when `x != 0`, and the arithmetic shift smears it into a full mask. No `cmp`, `jcc` or `setcc`.
- `mbedtls_ct_if` is `(c & a) | (~c & b)` written as `and/not/and/or`.
- `mbedtls_ct_uint_lt` uses a subtract-and-select on the sign bits, with no comparison instruction.

The ARM 32-bit asm for `bool` and `if` only applies when `MBEDTLS_CT_SIZE_32` is set, so 32-bit ARM with 64-bit `ct_uint` falls back to C.

**Block operations.** These don't use asm. `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads every byte through `volatile` pointers and ORs the XORs, so it always reads both buffers in full. `mbedtls_ct_memcpy_if` always reads `src1` and `src2` and builds the result with masks. `mbedtls_ct_zeroize_if` ANDs every byte with a mask.

## What happens on a compiler that can't support it

The asm is skipped, and the C fallback in `constant_time_impl.h` is used. That happens when:
- `MBEDTLS_HAVE_ASM` is undefined. The sanitizer CI component does this on purpose (`tests/scripts/components-sanitizers.sh`).
- The compiler isn't GCC-compatible. MSVC is the obvious case, and ARMCC 5 is excluded explicitly.
- The architecture is none of the four above, e.g. RISC-V, MIPS or PowerPC.

There is no `#error` and no warning. The header's own text says the fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an observation, not a guarantee. Nothing stops a future optimiser from turning the `volatile` read and masked arithmetic into a branch. The only thing that would catch it is the test harness below.

## How it is verified

Test suites mark secrets with `TEST_CF_SECRET` and `TEST_CF_PUBLIC`. Eight suites use them: `cipher`, `constant_time`, `constant_time_hmac`, `psa_crypto_constant_time`, `pkcs1_v15`, `bignum_core`, `bignum_mod_raw` and `base64`. Two harnesses use those annotations:
- **MemorySanitizer** (`component_test_memsan_constant_flow`, clang). Secrets are marked uninitialised, so a secret-dependent branch or address is reported. This build turns `MBEDTLS_HAVE_ASM` off, so **it tests the C fallback, not the asm**.
- **Valgrind** (`MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`, used in `components-configuration-crypto.sh`). Secrets are poisoned in memory, so the same class of leak is reported.

Caveat: the `framework` submodule is not checked out in this copy, so I could not read the `TEST_CF_*` macro definitions.

## How far it reaches

`mbedtls_ct_*` calls appear in 29 library files, about 286 call sites by grep. The main consumers:
- **RSA PKCS#1 v1.5 unpadding** (`mbedtls_ct_rsaes_pkcs1_v15_unpadding` in `rsa.c`), plus signature and hash comparisons.
- **TLS record handling** (`ssl_msg.c`): CBC padding checks, `mbedtls_ct_hmac`, and MAC comparison at lines 1798 and 2071.
- **AEAD and cipher tag checks**: `gcm.c:760`, `ccm.c:590`, `chachapoly.c:320`, `cipher.c:1298/1319`.
- **PSA verify paths**: `psa_crypto.c` (hash and MAC compares), `psa_crypto_mac.c:445`, and NIST KW unwrap.
- **Other**: `base64.c` (constant-flow decode), `ssl_cookie.c:354`, and `bignum_core`/`bignum`, which carry most of the arithmetic.

Where it stops:
- **ECP.** `ecp.c` makes no direct `mbedtls_ct_*` calls. Several entry points are documented "NOT constant-time": `mbedtls_ecp_mul_shortcuts`, `mbedtls_ecp_muladd` and `mbedtls_ecp_muladd_restartable`. The scalar-multiplication comb path is commented as constant-time, but its guarantee rests on the bignum layer.
- **Modular exponentiation.** `bignum.c` documents that the exponent-dependent path is not constant-time.
- **Length.** `mbedtls_ct_memcmp` is explicitly not constant-time with respect to `n`.
- **Vendored p256-m.** `3rdparty/p256-m` has its own constant-time story, outside this facility.

One index caveat: `dossier` reports `mbedtls_ct_memcmp` as `orphan` with 26 unresolved callers. That is wrong. The grep above finds more than a dozen real call sites, so the call graph is incomplete for this symbol. I used grep for the call-site list.