**Short answer:** mbedtls enforces constant time by code shape, not by a compiler guarantee. Branch-free arithmetic and volatile reads are the mechanism, and inline assembly pins the instructions on a few targets. Nothing checks the result at build time. Where assembly is unavailable, the library silently falls back to plain C that is only *observed* to compile branch-free. The facility is used in the places that handle secrets: RSA padding, TLS record MAC and padding checks, bignum comparisons, and the AEAD/cipher tag checks.

## How it is enforced at the instruction level

The core is `library/constant_time_impl.h`, with the public-facing API in `library/constant_time_internal.h` and `include/mbedtls/constant_time.h`.

- **Secret values are wrapped as masks.** `mbedtls_ct_condition_t` is an all-ones or all-zeros word (`MBEDTLS_CT_TRUE` / `MBEDTLS_CT_FALSE`). Every operation is `&`, `|`, `^`, `~`, or subtraction. Example: `mbedtls_ct_if` is `(cond & if1) | (~cond & if0)`.
- **`mbedtls_ct_bool(x)` turns a word into a mask without branching.** On AArch64, Thumb-2/ARM32, x86-64 and i386 it is a hand-written `neg/orr/asr` (or equivalent) sequence in `asm volatile`. Otherwise it uses `-(x | -(x>>1))` in plain C.
- **`mbedtls_ct_compiler_opaque(x)` stops the optimizer from proving values.** On the asm path it is an empty `asm volatile("" : "+r"(x))`. On the C path it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global. This is what prevents the compiler from folding a mask back into a branch.
- **Memory access is made data-independent with `volatile`.** `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile const unsigned char *`, so the early-exit-on-first-difference loop cannot be generated. It accumulates `diff |= x ^ y` and returns a value that is zero iff `diff` is zero. `mbedtls_ct_memcpy_if` and `mbedtls_ct_memcpy_offset` always read every source byte and select with masks. `mbedtls_ct_memcpy_offset` loops over the full offset range, so memory access does not depend on the secret offset.
- **Comparisons avoid `<` and `==` on secrets.** `mbedtls_ct_uint_lt` computes the sign of `x-y` with a MSB-based select. `mbedtls_ct_uint_ne` is `bool(x ^ y)`.

Be clear about what this does not guarantee. The compiler is still free to do anything with the C paths. The header comments say the C fallback was "observed" to be constant-time on recent gcc, clang and MSVC as of May 2023. That is an empirical observation, not a contract.

## What happens on a compiler or target that cannot support it

The selection is in `library/constant_time_impl.h:40-52`:

```c
#if defined(MBEDTLS_HAVE_ASM) && defined(__GNUC__) && (!defined(__ARMCC_VERSION) || ...)
#define MBEDTLS_CT_ASM
#if arm/thumb  -> MBEDTLS_CT_ARM_ASM
#elif aarch64  -> MBEDTLS_CT_AARCH64_ASM
#elif x86_64   -> MBEDTLS_CT_X86_64_ASM
#elif i386     -> MBEDTLS_CT_X86_ASM
#endif
#endif
```

- **Not GNU-compatible** (MSVC, old armcc, anything without `__GNUC__`): `MBEDTLS_CT_ASM` is undefined. Every primitive uses its C fallback.
- **`MBEDTLS_HAVE_ASM` undefined** (e.g. `configs/config-symmetric-only.h` has it commented out): same result, even on ARM or x86.
- **Unsupported architecture** (RISC-V, MIPS, etc.) with GNU: `MBEDTLS_CT_ASM` is defined but no per-arch macro matches, so the C fallback runs.
- **Assembly exists but the size doesn't match.** Each asm branch is also gated on `MBEDTLS_CT_SIZE_32` or `MBEDTLS_CT_SIZE_64`. A mismatch falls through to C.

Nothing emits a warning or an `#error` in these cases. The only compile-time check in this area is `#if (INT_MAX < INT32_MAX) #error "mbedtls_ct_memcmp() requires minimum 32-bit ints"` in `library/constant_time.c:99`. So on a non-supported target you get correct but less certainly constant-time code. Also note that without the asm path, `mbedtls_ct_zero` and the `volatile` loads become the only barrier, and `mbedtls_get_unaligned_volatile_uint32` (the fast path) is disabled.

## How far it reaches

About 29 library files reference the `mbedtls_ct_*` API, with roughly 416 occurrences. The main consumers are:

| Area | Where | What it does in CT |
|---|---|---|
| RSA PKCS#1 v1.5 unpadding | `library/rsa.c:420` `mbedtls_ct_rsaes_pkcs1_v15_unpadding` | Scans padding without branching on the padding bytes, zeroizes on failure, memmove-left to hide the plaintext offset |
| TLS record MAC and padding | `library/ssl_msg.c` (~lines 1495–2091) | CBC padding validation with `mbedtls_ct_uint_ge/eq` masks; `mbedtls_ct_hmac` runs the MAC over a fixed-size path; `mbedtls_ct_memcpy_offset` and `mbedtls_ct_memcmp` for the tag |
| Bignum | `library/bignum_core.c` / `.h`, `library/bignum.c`, `library/bignum_mod_raw.c` | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_lt_mpi_ct` (public in `bignum.h`), constant-time GCD/modinv |
| AEAD and cipher tags | `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `cipher.c`, `psa_crypto_cipher.c`, `psa_crypto_mac.c` | Tag comparison and padding removal |
| Other | `base64.c` (decode table lookups), `nist_kw.c` (`mbedtls_ct_memcmp_partial`), `psa_crypto_driver_wrappers.h` | Secret-dependent selection |

Two boundaries to note:
- The public `mbedtls_ct_memcmp` is documented as constant-time with respect to the data but **not** with respect to `n`. Callers must pass public lengths.
- `mbedtls_ct_memcmp_partial` and `mbedtls_ct_memcpy_if` document that they read a fixed amount regardless of skip or condition. The leakage they remove is data, not length.

I did not audit every call site, so I cannot say the library is free of secret-dependent branches elsewhere (for example, in the bignum code paths that are not in the list above).

## How it is tested

- Dedicated suites: `tests/suites/test_suite_constant_time.function`, `test_suite_constant_time_hmac.function`, and the `*constant_time*.data` files.
- `tests/scripts/components-configuration-crypto.sh:25-33` defines `test_with_valgrind_constant_time`, which runs those suites under Valgrind memcheck. `component_test_psa_assume_exclusive_buffers_valgrind_cf` (line 61) and a later component (line ~3019) turn on `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`. That is the "constant flow" mode: secret inputs are marked undefined so Valgrind reports any branch or index that depends on them. I did not read the framework code that implements the macro, so I can't confirm the exact mechanism beyond that.

The `*_valgrind_cf` components are the only automated check on branch-freedom at the binary level. The sanitizer components also reference the flag, but I did not trace those paths.