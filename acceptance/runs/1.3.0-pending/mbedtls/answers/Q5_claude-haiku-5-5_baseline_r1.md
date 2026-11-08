## Short answer

Constant time in mbedtls is a coding discipline backed by hand-written assembly for a few primitives, with a plain-C fallback that is not guaranteed. Nothing in the build checks the generated code. Verification is dynamic and only covers the paths the tests exercise. The facility is used heavily in RSA, bignum, cipher, base64, and the TLS MAC/padding paths, and not at all in AES, DES, ChaCha20, Poly1305, ECDSA, DHM, or ECJPAKE.

## How it is enforced at the instruction level

The public surface is `include/mbedtls/constant_time.h`, which exposes only `mbedtls_ct_memcmp`. The internal interface in `library/constant_time_internal.h` and `library/constant_time_impl.h` is the real mechanism. Every operation is branch-free arithmetic on a `mbedtls_ct_condition_t` mask, which is all-ones for true and zero for false:

- **`mbedtls_ct_bool(x)`** turns a value into a mask. On x86-64 it is `mov/neg/or/sar`, which sets the mask from the sign bit of `x | -x`.
- **`mbedtls_ct_if(c, a, b)`** is a bitwise mux: `(c & a) | (~c & b)`.
- **`mbedtls_ct_uint_lt`** and the other comparisons are built from subtraction and sign-bit extraction, with no comparison operators.
- **`mbedtls_ct_memcpy_if`** and **`mbedtls_ct_memcpy_offset`** always read every source byte and select by mask.

On the assembly paths, the compiler cannot see the value of a secret inside an `asm volatile` block, so it cannot turn the mask arithmetic back into a branch. Two further mechanisms keep the compiler from reasoning about values:

- `mbedtls_ct_compiler_opaque()` is an empty `asm volatile` with a `+r` constraint, or in the C path an XOR with a `volatile` zero (`mbedtls_ct_zero`).
- `mbedtls_ct_memcmp` casts its inputs to `volatile`, so it always reads both buffers in full with no early exit.

The assembly is selected in `constant_time_impl.h`. `MBEDTLS_CT_ASM` is defined only when `MBEDTLS_HAVE_ASM` is set and `__GNUC__` is present, excluding old armcc. The architecture macros then pick the path: ARM 32-bit and Thumb, AArch64, x86-64, or x86-32. Anything else falls through to C.

The key limit: the asm guarantees only the instructions inside each primitive. Nothing stops a caller from writing `if (secret)` in its own code. Correctness relies on callers always going through the primitives.

## What happens on an unsupported compiler or platform

Failure is silent. There is no `#error`, no warning, and no runtime flag. If `MBEDTLS_HAVE_ASM` is undefined, or the compiler is not GNU-compatible (MSVC, IAR, old armcc), or the architecture has no asm block (RISC-V, MIPS, and others), the C fallback is used. The header comment is explicit that this path has only been "observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an empirical observation, not a guarantee. A new compiler version can turn the mask arithmetic into a conditional branch or `cmov` and nothing in the build will notice.

Two more notes:

- `mbedtls_ct_memcmp` has a compile-time `#error` if `int` is narrower than 32 bits. That is the only architecture-level guard.
- The C path is tested. `component_release_test_valgrind_constant_flow_no_asm` in `tests/scripts/components-sanitizers.sh` runs the constant-flow suites with `MBEDTLS_HAVE_ASM` disabled under Valgrind.

## How it is verified

The verification is dynamic, not static. The test suites mark secrets with `TEST_CF_SECRET()` and `TEST_CF_PUBLIC()`, which mark memory as undefined. Valgrind memcheck or MemorySanitizer then reports any branch or address computation that depends on it. These are enabled with `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` or `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN`. Suites without `TEST_CF_` annotations are skipped in those components.

Things I could confirm and things I could not:

- **Confirmed:** the annotation scheme, the sanitizer components, and the no-asm Valgrind component all exist. `test_suite_constant_time.function` exercises the primitives directly.
- **Not confirmed here:** the `framework` submodule is an empty directory in this checkout (`git submodule status` shows it uninitialised), so `test/constant_flow.h` is missing. The constant-flow test suites cannot compile in this tree until the submodule is populated. I did not run any test.
- **Not checked:** I did not disassemble any build, so the claim that the asm survives into the object code rests on reading the source, not on inspecting output.

`SECURITY.md` is candid about the scope. It says protection against timing attacks is "limited", that the project "is moving towards a model of fully timing-invariant code, but has not reached this point yet", and that block ciphers "do not yet achieve full protection".

## How far it reaches

I counted occurrences of `mbedtls_ct_` in `library/` and read the relevant call sites. This is a grep count, so it is an approximation.

| Area | Files using the primitives | Notes |
|---|---|---|
| Bignum core | `bignum_core.c` (32), `bignum.c` (26), `bignum_mod_raw.c` | Basis for RSA and ECC |
| RSA | `rsa.c` (37) | Includes PKCS#1 v1.5 unpadding, `mbedtls_ct_memmove_left`, `mbedtls_ct_zeroize_if` |
| ECC | `ecp.c` via `mbedtls_mpi_safe_cond_assign` / `_swap` | Comb table lookup reads the whole table through `ecp_select_comb` |
| TLS record/handshake | `ssl_msg.c` (24), `ssl_tls12_*.c`, `ssl_tls13_*.c`, `ssl_tls.c`, `ssl_cookie.c` | MAC comparison, padding check, and related checks |
| Cipher layer | `cipher.c` (30), `psa_crypto_cipher.c`, `ccm.c`, `gcm.c`, `chachapoly.c`, `cmac.c` | Padding and tag comparison |
| Other | `base64.c` (21), `nist_kw.c` (`mbedtls_ct_memcmp_partial`), `psa_crypto.c`, `psa_crypto_mac.c` | |

About 21 `.c` files reach the primitives directly, plus several headers. The indirect path through `mbedtls_mpi_safe_cond_assign` means ECC reaches the facility without naming it.

Not covered: `aes.c`, `des.c`, `chacha20.c`, `poly1305.c`, `ecdsa.c`, `dhm.c`, `ecjpake.c`, `hmac_drbg.c`, `ctr_drbg.c`. Each has zero direct `mbedtls_ct_` references. Some may still go through bignum functions that are constant-time, such as ECDSA and DHM via bignum, so zero direct references does not prove those paths leak. I did not trace that. `aes.c` in particular has no constant-time protection in this tree, which matches the `SECURITY.md` warning about block ciphers.

Conditional compilation also narrows the reach. The RSA helpers exist only when `MBEDTLS_PKCS1_V15`, `MBEDTLS_RSA_C`, and not `MBEDTLS_RSA_ALT` are all defined. A platform that supplies its own RSA loses them.

## What would settle the open questions

- Populate the `framework` submodule, build the `valgrind_cf` and `memsan` components, and confirm the suites pass. That is the only real evidence that the assembly and C paths behave as claimed.
- Disassemble `mbedtls_ct_bool`, `mbedtls_ct_if`, and `mbedtls_ct_uint_lt` on the target compiler and confirm there are no `jcc` or `cmov` instructions that depend on the input.
- For the uncovered files, read `ecdsa.c`, `dhm.c`, and the ECJPAKE path to see whether they reach constant-time code through bignum, or whether they branch on secrets directly.