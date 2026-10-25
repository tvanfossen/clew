The short answer: constant-time behaviour in mbedtls is a convention the library implements with hand-written primitives and then checks by testing. The compiler is never asked to guarantee it, and nothing in the build verifies the emitted code.

## How it's enforced at the instruction level

The primitives live in `library/constant_time_impl.h`, with the public surface declared in `library/constant_time_internal.h`. Secret values are wrapped in `mbedtls_ct_condition_t` (all-ones or zero) and manipulated only through `mbedtls_ct_*` functions, so no secret-dependent `if` is needed.

- **Masks come from arithmetic, not comparisons.** `mbedtls_ct_bool(x)` on AArch64 is `neg s,x; orr x,s,x; asr x,x,63`, which yields all-ones if `x != 0` and zero otherwise. There are matching x86-64, i386 and 32-bit Arm/Thumb sequences.
- **Selection uses masks.** `mbedtls_ct_if` and friends are `and`/`or` combinations driven by that mask.
- **The optimiser is blocked from undoing it.** `mbedtls_ct_compiler_opaque(x)` is `asm volatile("" : "+r"(x))`, which hides the value so the compiler cannot prove it, fold the mask, or re-introduce a branch. Block memory ops (`mbedtls_ct_memcpy_if`, `mbedtls_ct_memcmp`) and `mbedtls_mpi_core_ct_uint_table_lookup` cover the cases where a secret controls a copy or an index.

## What happens on an unsupported compiler or target

Asm is selected only when `MBEDTLS_HAVE_ASM` is defined, the compiler is GNU-compatible, and the CPU is one of Arm/Thumb, AArch64, x86-64 or i386 (`constant_time_impl.h:40-52`). Otherwise `MBEDTLS_CT_ASM` is undefined and the code falls back to plain C:

- `mbedtls_ct_compiler_opaque(x)` becomes `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a global `volatile` zero (`constant_time.c:23-31`).
- Masks are computed with `-xo | -(xo >> 1)` and a sign-bit extraction.

The header says this fallback has been "observed to be constant-time" on recent gcc, clang and MSVC as of May 2023. That is an observation, not a guarantee. Nothing fails the build, and nothing warns that the target has lost the asm guarantee. A compiler or target that is not on the list silently gets the weaker path. Two other details matter: the C path costs a volatile read per operation, and MemorySanitizer builds are rejected if asm is enabled (`check_config.h:250`), because MSan needs the C path to see the data flow.

## How far it reaches

Usage is by file (count of `mbedtls_ct_` references):

| Area | Files (count) |
|---|---|
| Bignum | `bignum_core.c` (32), `bignum.c` (26), `bignum_mod_raw.c` (2) |
| RSA | `rsa.c` (37), including PKCS#1 v1.5 unpadding (`rsa.c:420`) |
| Symmetric/cipher | `cipher.c` (30, CBC padding), `ccm.c`, `gcm.c`, `chachapoly.c`, `cmac.c` (1 each) |
| TLS | `ssl_msg.c` (24, record MAC via `mbedtls_ct_hmac`), TLS 1.2/1.3 client/server, `ssl_misc.h` |
| Other | `base64.c` (21), `nist_kw.c` (4), `psa_crypto*.c`, `ssl_cookie.c` |

ECC reaches the facility indirectly: `ecp.c` has no direct `mbedtls_ct_` calls, but its comb multiplication and parity fix rely on the constant-time bignum core. I did not verify the ECDSA and ECDH paths line by line.

Gaps I found or inferred:
- `aes.c` has no `mbedtls_ct_` references. I did not check whether AES table lookups are protected some other way; the hardware AES paths avoid tables.
- The header describes a design intent for secret data. Public parsing paths (X.509, ASN.1) are not meant to be constant-time, so they are outside the facility by design.

## How it's checked

The only real enforcement is testing:

- `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` (clang MSan) and `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (memcheck) mark secret inputs as uninitialised. Any secret-dependent branch or index then fails the run. The CI components are `component_test_memsan_constant_flow` and `component_release_test_valgrind_constant_flow` in `tests/scripts/components-sanitizers.sh`, plus `test_with_valgrind_constant_time` in `components-configuration-crypto.sh`.
- Test suites are annotated with `TEST_CF_SECRET`/`TEST_CF_PUBLIC`, for example `tests/suites/test_suite_constant_time.function`.

Caveat: the `framework/` submodule is an empty directory in this checkout (`.gitmodules` points it at mbedtls-framework). The helper header `test/constant_flow.h` that the suites include is therefore missing here, so these suites and the MSan/Valgrind components will not build from this tree until the submodule is initialised. I did not attempt a build, so I have not run any of these checks.