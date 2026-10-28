## Short answer

Constant-time behaviour in mbedtls is a convention, not a verified guarantee. The helpers are branch-free by construction. Hand-written assembly pins the critical operations on the compilers and architectures that have it, and a plain-C fallback covers the rest with no guarantee. The facility is a small set of primitives that a few secret-dependent routines are written against. It does not cover the library as a whole.

## How it works at the instruction level

- **Masks, not branches.** Conditions are `mbedtls_ct_condition_t` values that are all-ones or all-zeros. `mbedtls_ct_uint_lt` (`library/constant_time_impl.h:271`) computes `x < y` with arithmetic and shifts, and `mbedtls_ct_if` (`:205`) selects with `(c & a) | (~c & b)`. There is no conditional jump on the secret.
- **Compiler opacity.** `mbedtls_ct_compiler_opaque` (`:85`) hides the value from the optimiser. With assembly it is `asm volatile("" : [x] "+r" (x))`. Without it, it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global (`library/constant_time.c:29`). This stops the compiler from folding a known constant into a branch.
- **Per-architecture assembly.** Hand-written `asm volatile` versions exist for AArch64, ARM Thumb/ARM32 (32-bit size), and x86-64 and x86-32. Each is selected by a macro chain. The base gate is `MBEDTLS_HAVE_ASM`, which defaults on (`include/mbedtls/mbedtls_config.h:52`). The compiler and CPU must also match `__GNUC__` or `__ARMCC_VERSION` and `__x86_64__`/`__amd64__` and so on (`constant_time_impl.h:40–52`).
- **Memory access.** `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers and ORs the XOR differences. It has no early exit. It is constant in the data, but not in the length `n`, as its own doc comment says.

## On a compiler that cannot support it

When `MBEDTLS_CT_ASM` is not defined, the code takes the `#else` branches:

- `mbedtls_ct_compiler_opaque` becomes the volatile-XOR trick above.
- `mbedtls_ct_bool` (`:120`) and `mbedtls_ct_uint_lt` fall back to plain C arithmetic. The source comment says that as of May 2023, trunk clang, gcc and MSVC v19 did not turn this into branches or conditional instructions. That is an observation about specific compiler versions. It is not a guarantee.
- `SECURITY.md` (Caveats) says the same thing in plain terms. Countermeasures exist to try to prevent compiler-introduced timing leaks, but "given the diversity of compilers, compiler options and target platforms", they cannot be guaranteed.

I found no build-time check in the index that refuses or warns when assembly is unavailable. The degradation looks silent. That is worth confirming in the build files, which the index does not cover.

## Machine-checked enforcement

The one automated check in the index is `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25`). It runs the `*constant_time*.data` suites under Valgrind. That run excludes `test_suite_constant_time_hmac.data` through `GLOBIGNORE`, even though `mbedtls_ct_hmac` is the most intricate consumer. I have not read the harness itself, so I cannot say what Valgrind is checking there. Passing that run is evidence about the tested build and tested inputs. It is not proof of constant-time output on every compiler.

## How far it reaches

Consumers found in the index:

| Area | Uses |
|---|---|
| Bignum core | `mbedtls_mpi_core_lt_ct` (`bignum_core.c:133`), `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_lt_mpi_ct` |
| Bignum | `mbedtls_ct_mpi_sign_if` |
| RSA | `mbedtls_ct_rsaes_pkcs1_v15_unpadding` |
| Cipher | `mbedtls_get_pkcs_padding` uses `mbedtls_ct_if` |
| TLS record layer | `mbedtls_ct_hmac` (`ssl_msg.c:65`), a constant-flow HMAC for CBC MAC checks that clones the hash context and finishes it at every candidate length |
| Base64 | `mbedtls_ct_base64_enc_char`, `mbedtls_ct_base64_dec_value` |
| Shared helpers | `mbedtls_ct_memcpy_if`, `mbedtls_ct_memcpy_offset`, `mbedtls_ct_zeroize_if` |

Limits:

- The index lists only the callers it could resolve. `mbedtls_ct_memcmp` has 26 unresolved callers, and `mbedtls_ct_bool` has 25. So this table is a sample, not a census.
- Code that does not go through these helpers gets no protection from them. Ordinary `if (secret)` branches elsewhere are outside the facility.
- `3rdparty/p256-m` and `3rdparty/everest` ship their own constant-time arithmetic. That is separate from this facility.

## What I could not settle from the index

- The generated machine code. Nothing here disassembles the output.
- Whether any build fails or warns when assembly is missing.
- The full caller list for the helpers, and what the valgrind harness actually asserts.