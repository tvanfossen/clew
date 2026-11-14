**Short answer:** the library has no compiler or machine-code check of constant time. Three things carry the claim: inline-assembly barriers and branch-free sequences on four architectures, a plain-C fallback everywhere else, and valgrind/MSan tests that catch some secret-dependent behaviour at runtime. The header says the C fallback has only been *observed* to be constant-time, and `SECURITY.md` says the protection is incomplete.

## 1. How it is enforced at the instruction level

Everything is built on two pieces in `library/constant_time_impl.h`:

- **`mbedtls_ct_compiler_opaque(x)`** (line 85) stops the compiler from knowing a value. With assembly it is `asm volatile("" : [x] "+r"(x))`, an empty statement that forces `x` into a register and claims it was modified. Without assembly it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global defined in `library/constant_time.c:29`.
- **The mask primitives.** `mbedtls_ct_bool(x)` turns any non-zero value into an all-ones mask (`MBEDTLS_CT_TRUE`) or zero. `mbedtls_ct_if`, `mbedtls_ct_uint_lt` and the other comparisons are built from masks and bitwise operations. On AArch64, 32-bit Arm/Thumb, x86-64 and i386 each primitive is hand-written inline assembly (lines 130–348), so the compiler never sees a branch or conditional instruction. The C versions at lines 184–198 and 351–378 are the fallback.

Secret data is never compared with `==`, `<` or `if`. Operations are phrased as masks: `mbedtls_ct_memcpy_if` (`library/constant_time.c:169`) reads both sources and blends them with `(src1 & mask) | (src2 & ~mask)`. `mbedtls_ct_memcmp` (line 67) reads both buffers as `volatile`, so the compiler cannot exit early, and returns the OR of all XORs.

The assembly is selected by `constant_time_impl.h:40–52`. It needs `MBEDTLS_HAVE_ASM`, a GNU-compatible compiler (not MSVC, not ARMCC 5), and one of the four supported architectures. The arch-specific macros only add the hand-written sequences; the generic barrier is used whenever the other conditions hold.

## 2. A compiler that cannot support it

There is no build error and no warning. The fallback is chosen silently when any of these hold:

| Condition | Result |
|---|---|
| `MBEDTLS_HAVE_ASM` not defined | C fallback everywhere, including x86-64 |
| MSVC, IAR, or ARMCC 5 | `__GNUC__` check fails, so C fallback |
| GCC/Clang on an architecture without a hand-written sequence (e.g. RISC-V) | Generic asm barrier, C arithmetic for the rest |

The C fallback is slower, since every opaque call is a volatile load. Its constant-time behaviour depends on the optimizer not turning the mask arithmetic back into branches. The header records only that it was observed on recent gcc, clang and MSVC as of May 2023. `SECURITY.md:109–111` says compiler-introduced timing leaks are possible, that the countermeasures "may not be complete", and that only `-O2`/`-Os` are in scope.

The test matrix does cover the fallback. `tests/scripts/components-sanitizers.sh` has a `valgrind_constant_flow_no_asm` component alongside the assembly one. That is evidence the fallback is exercised, not that it is branch-free on every compiler.

## 3. How it is checked

- `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (`include/mbedtls/mbedtls_config.h:2142`) marks secrets as undefined, so memcheck reports any branch or address that depends on them. Run through `tests/scripts/components-configuration-crypto.sh` on the `*constant_time*` suites.
- `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` does the same with clang's MemorySanitizer. `include/mbedtls/check_config.h:250` refuses to build MSan together with `MBEDTLS_HAVE_ASM`, because MSan cannot see inline assembly.

These tests only see what they execute, on the compilers and inputs CI uses. Nothing inspects the generated machine code.

## 4. How far it reaches

The `mbedtls_ct_*` calls are spread across 29 library files, about 286 call sites:

| Area | Files (call sites) | Role |
|---|---|---|
| Big-number core | `bignum_core.c` (22), `bignum.c` (21), `bignum_mod_raw.c` (2) | Secret-scalar arithmetic, conditional assign and swap |
| RSA | `rsa.c` (29) | PKCS#1 v1.5 unpadding with no branch on padding validity |
| TLS CBC records | `ssl_msg.c` (22), `cipher.c` (25) | `mbedtls_ct_hmac` computes the MAC over a fixed maximum length; padding removal is branch-free |
| Encoding | `base64.c` (21) | Constant-time character decode and encode |
| Other | `psa_crypto.c` (7), `ssl_tls12_server.c` (7), `nist_kw.c` (4), and single calls in `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `psa_crypto_mac.c` | Mostly tag and secret comparisons |

ECC reaches the facility indirectly. `ecp.c` has no direct `mbedtls_ct_` calls. It uses `mbedtls_mpi_safe_cond_assign` and `mbedtls_mpi_safe_cond_assign`/`_swap` (lines 1202–1215, 2143), which are built in `bignum.c`. The comb table lookup reads the whole table to resist cache timing (line 2020), and the comments at lines 2734, 2769 and 2873 say some functions are explicitly "NOT constant-time". I did not check which functions those comments cover.

Places the facility does not reach, per `SECURITY.md`:

- **Software AES, Camellia, ARIA and DES** use lookup tables and are called out as timing-vulnerable. Hardware AES (AES-NI, AES-CE, PadLock) is the documented workaround.
- **X25519 via Everest** only protects against remote timing attacks.
- **`mbedtls_ct_memcmp_partial`** is constant-time in the buffer contents but not in the length.
- **`mbedtls_ct_memcpy_if`** branches on whether `src2` is `NULL`.

## Caveats

- I did not build the library or run valgrind/MSan; these answers come from reading the source and the CI scripts.
- Constant-time claims rest on the compiler respecting the masks. The only automated evidence is the valgrind and MSan suites, which run on CI's compilers and optimisation levels.