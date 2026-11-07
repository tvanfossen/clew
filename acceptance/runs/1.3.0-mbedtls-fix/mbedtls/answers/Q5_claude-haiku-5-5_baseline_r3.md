**Short answer:** mbedtls does not verify constant-time behaviour at build time. Its guarantees rest on hand-written assembly for four architectures, a C fallback that relies on compiler behaviour, and opt-in sanitizer tests. The facility reaches the secret-dependent parts of TLS, RSA, AEAD, and base64, but several sensitive paths are explicitly not constant-time.

## How it is enforced at the instruction level

The primitives live in `library/constant_time_internal.h` (declarations) and `library/constant_time_impl.h` (static inline definitions). Only `mbedtls_ct_memcmp` is public, in `include/mbedtls/constant_time.h`.

There are three layers:

1. **Opaque values.** `mbedtls_ct_compiler_opaque()` (`constant_time_impl.h`) hides a value from the optimizer. On GCC-compatible builds it is an empty `asm volatile` with a read-write constraint. Otherwise it XORs with `mbedtls_ct_zero`, a `volatile` zero defined in `constant_time.c`.
2. **Branch-free masks.** `mbedtls_ct_bool` turns an integer into an all-ones or all-zeros mask using `neg/or/asr`. `mbedtls_ct_if` selects with `and/not/and/or`. `mbedtls_ct_uint_lt` uses a subtract-and-sign-bit trick. The AArch64, 32-bit ARM, x86-64 and x86-32 variants are hand-written asm. Other targets use plain C.
3. **Block operations and callers.** `mbedtls_ct_memcmp` reads through `volatile` pointers so the loop cannot exit early. `mbedtls_ct_memcpy_if`, `mbedtls_ct_zeroize_if` and `mbedtls_ct_memmove_left` cover conditional copies. Callers are the real consumers, for example the TLS 1.2 CBC padding check in `ssl_msg.c` (~L1916–1978) and the RSA PKCS#1 v1.5 unpadding in `rsa.c` (~L420).

The asm is the only part the library can actually pin. Everything else depends on the compiler not reintroducing a branch.

## What happens on a compiler that cannot support it

The asm is gated by `MBEDTLS_HAVE_ASM`, GNU-compatible `__GNUC__`, and ARMCC ≥ 6:

```
MBEDTLS_HAVE_ASM && __GNUC__ && !armcc5 ──► MBEDTLS_CT_ASM
   ├─ arm/thumb + 32-bit size  ──► ARM asm
   ├─ aarch64 + 32/64-bit size ──► AArch64 asm
   ├─ x86-64                   ──► x86-64 asm
   ├─ i386 + 32-bit size       ──► x86 asm
   └─ anything else (e.g. RISC-V GCC) ──► generic opaque barrier, C masks
MBEDTLS_CT_ASM undefined (MSVC, HAVE_ASM off, ...) ──► pure C + volatile mbedtls_ct_zero
```

- **It does not fail to build.** There is no `#error` on the fallback path.
- **Correctness is preserved.** The C code computes the same results.
- **The timing guarantee is weaker and silent.** The C fallback is described as "observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an observation, not a guarantee, and I found no build-time or runtime warning when it is in use.
- **ARM32 with 64-bit `mbedtls_ct_uint_t`** also drops to C, because the ARM asm is only defined for the 32-bit size.
- **MemorySanitizer builds** are forced off asm: `check_config.h` errors if `MBEDTLS_HAS_MEMSAN` and `MBEDTLS_HAVE_ASM` are both set.

`SECURITY.md` ("Compiler-induced side channels") says the same thing in policy form. Prevention "may not be complete", and the project will only treat exploitable leaks as vulnerabilities at common optimization levels (`-O2`/`-Os`), not `-O3`/`-Oz`.

## How far it reaches

**Used in (secret-dependent paths):**
- `bignum_core.c` (32 call sites), `bignum.c`, `bignum_mod_raw.c`, and `bignum_core.h` comparison and zero-check helpers
- `rsa.c` (37): PKCS#1 v1.5 unpadding
- `ssl_msg.c` (24): CBC padding and the Lucky13-style `mbedtls_ct_hmac`, plus `mbedtls_ct_memcmp` for the record MAC
- `cipher.c` (30): CBC unpadding
- `base64.c` (21), `psa_crypto.c`, `psa_crypto_cipher.c`, `psa_crypto_mac.c`
- Tag comparisons in `ccm.c`, `gcm.c`, `cmac.c`, `chachapoly.c`, `nist_kw.c`
- `ecp.c`: comb-table selection (`ecp_select_comb`) and the parity fix in the scalar recode

**Explicitly not constant-time:**
- `mbedtls_ecp_muladd_restartable` (`ecp.h` ~L1023 says so) and `mbedtls_ecp_mul_shortcuts` (`ecp.c` ~L2734, "NOT constant-time")
- A modular-exponentiation helper in `bignum_core.h` (~L643) warns it is not constant-time with respect to the exponent
- `mbedtls_ct_memcmp` is not constant-time with respect to the length `n`, which is documented in the header
- Table-based AES, CAMELLIA, ARIA and DES, which `SECURITY.md` says are "vulnerable to timing attacks"

`SECURITY.md` also limits the threat model to "publicly documented attack techniques" and says the library "has not reached" fully timing-invariant code.

## How it is tested

- `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (memcheck, secrets marked undefined) and `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` (clang MSan, no asm) are both **off by default**. `tests/scripts/components-sanitizers.sh` runs them in CI.
- `tests/suites/test_suite_constant_time*.function` check functional results, and their header comment says they are meant to be run under MSan or valgrind to catch non-constant-time code.
- The shared harness `test/constant_flow.h` lives in the `framework` submodule, which is **not checked out** in this repo, so I could not read it. The claims about how it marks secrets come from the test-suite comments, not from the harness code.

**Bottom line:** the instruction-level guarantee exists only where hand-written asm is used. Everywhere else it is a best-effort C pattern, checked by optional sanitizer runs rather than by the default build.