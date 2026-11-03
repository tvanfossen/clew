## Short answer

Constant-time behaviour in mbedtls is mostly not enforced at the instruction level. The library tries to force it with inline assembly on a few architectures, with a portable C fallback elsewhere. The fallback has no compile-time check. What actually gates it is Valgrind/MSan "constant flow" tests in CI. The facility reaches the RSA, TLS record, cipher, AEAD, base64 and bignum paths, but not the ECC or DH code.

## How it is enforced at the instruction level

Everything lives in `library/constant_time_impl.h` (primitives), `library/constant_time_internal.h` (types and declarations) and `library/constant_time.c`.

1. **Mask-based design.** Conditions are full-width masks (`mbedtls_ct_condition_t` is all-ones or all-zeros). `mbedtls_ct_bool(x)` turns a value into a mask with no branches. Selects, comparisons and error accumulation are then done with `&`, `|` and `^` (for example `mbedtls_ct_uint_if`, `mbedtls_ct_error_if`).
2. **Assembly pins the instructions.** `constant_time_impl.h:42-54` defines `MBEDTLS_CT_ASM` only when `MBEDTLS_HAVE_ASM` is set and the compiler is GNU-style (`__GNUC__`, not old armcc). Per-architecture branches then select `MBEDTLS_CT_ARM_ASM`, `MBEDTLS_CT_AARCH64_ASM`, `MBEDTLS_CT_X86_64_ASM` or `MBEDTLS_CT_X86_ASM`. Each one has hand-written `neg`/`orr`/`asr` (or `sar`) sequences in `mbedtls_ct_bool` (around `constant_time_impl.h:120`). Those sequences are the only place the instructions themselves are fixed.
3. **Optimizer barrier.** `mbedtls_ct_compiler_opaque()` (`constant_time_impl.h:85-93`) wraps values in `asm volatile("" : "+r"(x))` so the compiler cannot prove a value and fold the mask back into a branch. It is a barrier against folding, not a timing guarantee.
4. **Volatile zero for the fallback.** Without `MBEDTLS_CT_ASM`, `constant_time.c:23-29` defines `volatile mbedtls_ct_uint_t mbedtls_ct_zero = 0`, and the barrier becomes `x ^ mbedtls_ct_zero`. The mask fallback in `mbedtls_ct_bool` (`y = (-xo) | -(xo >> 1)`, then take the sign bit) is plain C.
5. **Constant-time memcmp.** `mbedtls_ct_memcmp` (`constant_time.c`) reads both buffers through `volatile` pointers so the loop cannot exit early. Its public header says it is not constant with respect to `n`.

## What happens on a compiler that cannot support it

- **No build failure, no warning.** The only `#error`s in these files are for an unaligned-volatile helper that has no asm path (`constant_time.c:60`) and for `mbedtls_ct_memcmp` needing 32-bit ints (`constant_time.c:105`). Neither fires when assembly is simply unavailable.
- **Silent degradation.** Without `MBEDTLS_HAVE_ASM`, with MSVC (no `__GNUC__`), or on an architecture with no asm branch (RISC-V, Xtensa and similar), the code uses the C mask fallback. Nothing tells the user the guarantee is weaker.
- **The fallback's guarantee is an observation, not a contract.** The source comment says the C form "does not get optimised into conditional instructions or branches by trunk clang, gcc, or MSVC v19" as of May 2023. That is a dated claim about compilers, not something the code enforces.

## How far it reaches

`mbedtls_ct_` symbols are used in about 30 library files. Counts from grep, excluding the headers:

| File | Uses | What it protects |
|---|---|---|
| `rsa.c` | 37 | PKCS#1 v1.5 unpadding (`mbedtls_ct_rsaes_pkcs1_v15_unpadding`) |
| `bignum_core.c` / `bignum.c` / `bignum_mod*.c` | 32 / 26 / 3 | MPI compare, zero test, conditional select |
| `cipher.c` | 30 | CBC padding removal |
| `ssl_msg.c` | 24 | TLS record MAC verify (`mbedtls_ct_hmac`) and padding |
| `base64.c` | 21 | Encode/decode character mapping |
| `psa_crypto.c` | 9 | MAC/hash tag compares (`mbedtls_ct_memcmp`) |
| `ssl_tls12_server.c` | 8 | Premaster-secret length and version check (around line 3409) |
| `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `nist_kw.c` | 1–4 each | Tag comparison |

**Not reached:** `ecp.c`, `ecp_curves.c`, `ecdsa.c` and `dhm.c` have zero `mbedtls_ct_` references. ECC uses its own comb multiplication (`ecp_select_comb`) and `mbedtls_mpi_safe_cond_assign` / `safe_cond_swap` (`ecp.c` around lines 1202–1215 and 2010–2143). I did not trace those helpers down to the `mbedtls_ct_` layer, so I cannot say whether they are built on it. The 3rdparty `p256-m` has its own `MUL64_IS_CONSTANT_TIME` gate, separate from this module.

## How it is tested

- `test_with_valgrind_constant_time` in `tests/scripts/components-configuration-crypto.sh:25-32` runs the `*constant_time*.data` suites under Valgrind memcheck with a `valgrind_cf` configuration. The suites mark secrets with `TEST_CF_SECRET` and `TEST_CF_PUBLIC` (`test_suite_constant_time.function:7`). Marking a secret as undefined means any secret-dependent branch or address shows up as an uninitialised-value error.
- Many other suites include `test/constant_flow.h` (cipher, bignum, base64, pkcs1_v15, ssl, psa constant-time).
- **Gap:** `framework/tests/include/test/constant_flow.h` is not present in this checkout, so I could not read how `TEST_CF_SECRET` is implemented. The framework submodule may not be initialized here.
- Nothing in CI tests the C fallback specifically. The fallback is only exercised when the configuration turns `MBEDTLS_HAVE_ASM` off, and the Valgrind components set it on.

## Bottom line

The guarantee holds only where the hand-written assembly is used (the mask primitives on Arm, AArch64 and x86) and where the Valgrind constant-flow tests run. Elsewhere the library silently falls back to C and relies on the optimizer leaving the masks alone. ECC constant-time behaviour sits in a different layer that this facility does not cover.