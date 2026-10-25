## Short answer

Constant-time behaviour in mbedtls is a coding discipline backed by a small primitive API, not something the compiler verifies. The primitives compute branch-free masks, and inline asm on four architectures keeps the compiler from undoing them. On other compilers or CPUs the code silently falls back to plain C, and the property is then only "observed" rather than guaranteed. The facility is used in the places where secrets are handled (RSA/PKCS#1 unpadding, TLS record MAC and CBC-padding checks, AEAD tag comparison, bignum conditional ops, ECC fixed-base table reads). It does not cover everything: some bignum and ECC paths are explicitly documented as not constant-time, and I found no constant-time annotation on the software AES path.

## How it is enforced at the instruction level

The core is `library/constant_time_internal.h` (declarations and design notes) and `library/constant_time_impl.h` (definitions), with out-of-line functions in `library/constant_time.c`.

- **Opaque condition type.** `mbedtls_ct_condition_t` is an all-ones or all-zeros mask, and `mbedtls_ct_compiler_opaque()` hides constants from the optimiser. With asm available it is an empty `asm volatile` that takes and returns the value. Otherwise it XORs with a global `volatile mbedtls_ct_zero`.
- **Boolean from integer.** `mbedtls_ct_bool(x)` computes `neg x | x`, then an arithmetic shift of the sign bit. That gives all-ones if `x != 0` and zero otherwise, with no compare or branch. The AArch64, ARM and x86 variants are hand-written asm; the generic version is C arithmetic.
- **Select.** `mbedtls_ct_if` is `(c & a) | (~c & b)`, again in asm on the supported targets.
- **Memory compare.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers, ORs all XOR differences together, and never exits early. It also `#error`s on platforms with `int` narrower than 32 bits.
- **Block operations.** `mbedtls_ct_memcpy_if`, `mbedtls_ct_memcpy_offset` and `mbedtls_ct_memmove_left` always touch the same memory regardless of the secret.

## What happens on a compiler or CPU that can't support it

The asm path is taken only when all three hold: `MBEDTLS_HAVE_ASM` is defined, the compiler is GCC-compatible (`__GNUC__`, and not ARMCC 5), and the architecture is ARM/Thumb, AArch64, x86-64 or x86 (`constant_time_impl.h:40-52`). Everything else takes the C fallback:

| Situation | Result |
|---|---|
| `MBEDTLS_HAVE_ASM` off | Plain C everywhere; `mbedtls_ct_zero` used to hide constants |
| MSVC, IAR, ARMCC5 | Same C fallback |
| GCC/Clang on an unlisted arch (e.g. RISC-V) | `compiler_opaque` uses a generic asm barrier, but `bool`/`if` use C |
| Any of the above | No `#error`, no warning |

The header's own comment says the C fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023." That is an empirical statement, not a guarantee. The C fallback is also slower: every call does a volatile load, and every TU links against `mbedtls_ct_zero`.

## How it is actually checked

Verification is by testing, not by the build:

- `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (`include/mbedtls/mbedtls_config.h:2126`) runs test suites under Valgrind memcheck with secrets marked uninitialised, so a secret-dependent branch shows up as an error. Driven by `tests/scripts/components-configuration-crypto.sh` and `components-sanitizers.sh`.
- `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` does the same with clang MemorySanitizer. `check_config.h:250` makes MSan and the asm path mutually exclusive, so MSan runs use the C fallback.
- `tests/suites/test_suite_constant_time.function` instruments tests with `TEST_CF_SECRET`/`TEST_CF_PUBLIC`. Those macros live in the `framework` submodule, which is empty in this checkout, so I could not read them.

## How far it reaches

Counts are `mbedtls_ct_` references per file.

| Area | File (refs) | What is constant-time |
|---|---|---|
| Primitives | `constant_time.c` (17), `constant_time_impl.h` | All of the above |
| Bignum core | `bignum_core.c` (32), `bignum.c` (26) | Conditional assign/swap, `lt_ct`, table lookup for windowed exponentiation, Montgomery multiply, modular inverse |
| ECC | `ecp.c` (wrapper macros, no direct `mbedtls_ct_` calls) | Fixed-base comb reads the whole table (`ecp_select_comb`); parity fix via `mbedtls_mpi_safe_cond_assign` |
| RSA | `rsa.c` (37) | PKCS#1 v1.5 unpadding, decrypt, sign |
| TLS record layer | `ssl_msg.c` (24), `ssl_tls12_*`, `ssl_tls13_*` | CBC padding check, `mbedtls_ct_hmac`, MAC compare via `mbedtls_ct_memcmp` |
| Ciphers | `cipher.c` (30) | CBC padding removal, tag check |
| AEAD tags | `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c` (1 each) | Tag comparison only |
| Other | `base64.c` (21), `nist_kw.c` (4), `psa_crypto*.c` | Base64 char mapping without secret-indexed tables; partial memcmp; PSA wrappers |

Places that are explicitly not constant-time:

- `bignum_core.c` `exp_mod`: not constant-time with respect to the exponent when `E_public` is `MBEDTLS_MPI_IS_PUBLIC` (see `mbedtls_mpi_exp_mod_unsafe` in `bignum.c:1744`).
- `ecp.c` `mbedtls_ecp_mul_shortcuts` and `mbedtls_ecp_muladd_restartable`: marked "NOT constant-time" (lines ~2734, ~2769).
- The software AES path: `aes.c` has no `mbedtls_ct_` use or constant-time comment, and I did not audit its table lookups. Treat it as outside the facility.

Hardware-level effects, such as variable-latency multiply instructions or cache behaviour, are outside what the primitives can promise. I did not check that dimension.

## Caveats

- I did not build or run anything. The conclusions come from reading the code and the test scripts.
- The `framework` submodule is missing, so I could not inspect the constant-flow test macros or the Valgrind/MSan harness internals.