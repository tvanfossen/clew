## Short answer

Constant-time behaviour is not enforced by the compiler or by any build check. It rests on three things: hand-written assembly for a few primitives on four architectures, a plain-C fallback everywhere else, and tests that use Valgrind/MSan to catch secret-dependent branches. Nothing fails at build time if the assembly path is unavailable; the code quietly falls back.

## How it works at the instruction level

All secret-dependent logic is built from branch-free bit masks. `mbedtls_ct_condition_t` is an all-ones or all-zeros word, and the public API (`include/mbedtls/constant_time.h` and the internal `library/constant_time_internal.h`) is organised as:

- **Booleans:** `mbedtls_ct_uint_eq`, `_lt`, `_bool`, and so on, returning a mask.
- **Selection:** `mbedtls_ct_uint_if`, `_if_else_0`, used in place of `x ? a : b`.
- **Block operations:** `mbedtls_ct_memcpy_if`, `mbedtls_ct_memcmp`, and related, which touch every byte regardless of the condition.

Three mechanisms keep the compiler from undoing this:

1. **Hand-written asm primitives.** `library/constant_time_impl.h` defines `mbedtls_ct_bool` (negate, OR, arithmetic shift to build the mask) and `mbedtls_ct_if` (AND/NOT/AND/OR select) in `asm volatile` for ARM/Thumb, AArch64, x86 and x86-64.
2. **An opacity barrier.** `mbedtls_ct_compiler_opaque()` uses an empty `asm volatile("" : "+r"(x))` so the compiler cannot prove a mask's value. The fallback instead XORs with a global `volatile mbedtls_ct_zero`.
3. **Volatile reads in `mbedtls_ct_memcmp`** (`library/constant_time.c`). Both buffers are read through `volatile` pointers, so the loop cannot exit early on the first mismatch. The result is a single OR-accumulated difference.

## What happens on an unsupported compiler or architecture

The selection is in `constant_time_impl.h` (lines 40–52):

```
MBEDTLS_HAVE_ASM && __GNUC__ (not old armcc)  ->  MBEDTLS_CT_ASM
   + arch: arm/thumb | aarch64 | x86_64 | i386  ->  per-arch asm
otherwise                                     ->  plain C fallback
```

- **Compiler:** Anything without GNU-style `asm` (MSVC, IAR, old armcc) uses the C fallback. The fallback has a MSVC-specific warning suppression for the unary minus.
- **Architecture:** RISC-V, MIPS, and other targets get the C fallback.
- **Config:** Defining the asm-disable switch (`MBEDTLS_HAVE_ASM` off) forces the fallback everywhere.
- **Failure mode:** The fallback's own comment says it "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an empirical observation, not a guarantee. Nothing is detected at runtime, and nothing warns at build time.

The only hard `#error`s in this area are for `int` narrower than 32 bits in `mbedtls_ct_memcmp`, and for the unaligned-volatile helper if ARM/AArch64 asm is selected without an implementation.

## How it is verified

The verification is test-side, not compile-side:

- Test suites mark data with `TEST_CF_SECRET` / `TEST_CF_PUBLIC` (for example `tests/suites/test_suite_constant_time.function`).
- `tests/scripts/components-sanitizers.sh` builds with `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` or `_MEMSAN`, and runs only suites that carry annotations. Valgrind/MSan then reports any branch or memory index that depends on secret (uninitialised-marked) data.

Caveat: the `framework/` submodule is empty in this checkout, so the macro definitions are not here. I could not read their implementation. I also did not build or run any of these tests.

## How far it reaches

Counts of `mbedtls_ct_` references per library file (from grep; I did not read most call sites):

| File | Refs | File | Refs |
|---|---|---|---|
| rsa.c | 37 | psa_crypto.c | 9 |
| bignum_core.c | 32 | ssl_tls12_server.c | 8 |
| cipher.c | 30 | nist_kw.c | 4 |
| bignum.c | 26 | psa_crypto_cipher.c | 4 |
| ssl_msg.c | 24 | gcm, ccm, chachapoly, cmac, ssl_cookie, psa_crypto_mac | 1 each |
| base64.c | 21 | | |

Observations:

- **Bignum and RSA are the core consumers.** `ecp.c` has no direct `mbedtls_ct_` calls. It gets constant-time behaviour from `mbedtls_mpi_safe_cond_assign` / `safe_cond_swap` in the comb and ladder paths, around lines 1200–1215 and 2100–2140. Some ECP functions are explicitly marked "NOT constant-time" (around lines 2734, 2769, 2873), so the facility is not applied uniformly.
- **Verification paths:** `psa_crypto.c` uses `mbedtls_ct_memcmp` for hash and MAC comparison.
- **TLS record handling:** `ssl_msg.c` is a heavy user, which fits the CBC padding and MAC checks. I inferred that from the file's role, not from reading those call sites.
- **Not covered by this facility:** Code outside these call sites is ordinary C with no guarantee. Cache-timing effects from table lookups are not addressed here. I did not audit AES or other table-based code, so I can't say whether it is covered.

## Open items

- To confirm the test macros' behaviour, the `framework/` submodule needs to be initialised.
- To confirm the TLS padding claim, read the `ssl_msg.c` call sites.