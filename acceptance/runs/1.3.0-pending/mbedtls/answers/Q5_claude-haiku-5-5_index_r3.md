**Short answer:** the constant-time guarantee is not enforced by the compiler or by any build-time check. It rests on three things: hand-written assembly for the primitives on four architectures, a plain-C fallback everywhere else that is only empirically constant-time, and dynamic tests that catch secret-dependent branches on the paths they exercise. The facility covers bignum, RSA, cipher padding, TLS record handling, base64 and a few others. It does not appear in the ECC or AES code in this checkout.

## How it is enforced at the instruction level

All primitives live in `library/constant_time_impl.h` and are declared with their contract in `library/constant_time_internal.h`. The contract (`constant_time_internal.h:20-63`) says the operations are "likely to result in" branch-free code, which is an honest hedge.

- **Mask generation** (`mbedtls_ct_bool`, `impl.h:120-203`). A non-zero value becomes an all-ones mask. On AArch64 this is `neg / orr / asr 63`; on 32-bit Arm it is `negs / orrs / asrs #31`; on x86-64 it is `mov / neg / or / sar $63`. Every bit of arithmetic is inside `asm volatile`, so the compiler cannot turn it into a `jcc` or a `csel`.
- **Selection** (`mbedtls_ct_if`, `impl.h:205-269`) is an `and / not / and / or` blend under the mask, again in asm on the same architectures.
- **Comparison** (`mbedtls_ct_uint_lt`, `impl.h:271-380`) is built from subtract-and-borrow sign-bit arithmetic, with the asm variants written out per architecture.
- **Hiding values from the optimiser.** `mbedtls_ct_compiler_opaque` (`impl.h:85-93`) is an empty asm with a `+r` constraint when asm is available. Otherwise it XORs with a `volatile` zero (`constant_time.c:23-30`). That stops the compiler from proving a value at compile time and folding a branch away.
- **Memory operations** (`constant_time.c`). `mbedtls_ct_memcmp` (`:67-116`) reads both buffers through `volatile` pointers and ORs all differences, so there is no early exit. `mbedtls_ct_memcpy_if` (`:169-212`) always reads both sources and blends with masks. `mbedtls_ct_memcpy_offset` (`:214-227`) loops over every possible offset, so the access pattern depends only on `offset_min`/`offset_max`.

Even the asm does not control the hardware. Nothing here addresses cache timing, variable-latency division, or speculative execution.

## What happens on a compiler that cannot support it

It falls back silently. There is no `#error`, no warning, and no runtime check.

The asm path is selected only when `MBEDTLS_HAVE_ASM` is defined and the compiler is GCC-compatible (`impl.h:40-52`). `MBEDTLS_HAVE_ASM` is a user switch (`mbedtls_config.h:52`), so any build that undefines it, such as the `config-symmetric-only` profile, takes the C path. The asm also covers only four families: Arm (32-bit and Thumb), AArch64, x86-64 and i386. MSVC, IAR, armcc 5, RISC-V and others fall through to the C path in each function.

The C path is claimed to be constant-time only because "this has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h:57-59`). That is a snapshot observation with no guarantee. A future optimiser could reintroduce a branch and nothing in the build would notice, except the valgrind/MSan tests below.

Sanitizer builds are the one case that is refused outright. `check_config.h:250-251` errors if MemorySanitizer is combined with `MBEDTLS_HAVE_ASM`. So the MSan constant-flow test runs the C fallback, not the asm.

## How it is tested

These are dynamic checks, not static ones.

- `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` and `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` (`mbedtls_config.h:2109-2142`) are off by default. They are exercised by `components-sanitizers.sh` (`:72-150`), including a `_no_asm` variant (`:105`) and an MSan variant (`:33`). The `skip_suites_without_constant_flow` helper restricts runs to suites that carry constant-flow annotations.
- `tests/suites/test_suite_constant_time*.function` and similar suites exercise the primitives directly.
- The annotation macros that mark secret inputs (`TEST_CF_SECRET` and friends) are not defined in this checkout. The tests refer to them but I could not find their definitions, so they likely come from the external test framework. I could not verify how they are implemented.

Valgrind and MSan only flag a secret-dependent branch on a path the test actually executes with secret data. Coverage is only as good as the annotations.

## How far it reaches

Dossier and grep show 286 `mbedtls_ct_*` call sites across 29 library files. Roughly, by file:

| Area | Files (call sites) |
|---|---|
| Bignum | `bignum_core.c` (22), `bignum.c` (21), `bignum_mod_raw.c` (2) |
| RSA | `rsa.c` (29) |
| Cipher padding | `cipher.c` (25); `mbedtls_get_pkcs_padding` calls `mbedtls_ct_if` |
| TLS | `ssl_msg.c` (22), `ssl_tls12_server.c` (7), others |
| Base64 | `base64.c` (21) |
| PSA | `psa_crypto.c` (7), `psa_crypto_cipher.c` (3), others |
| Other | `nist_kw.c` (4); single calls in `gcm.c`, `ccm.c`, `cmac.c`, `chachapoly.c` |

These are the places where it matters most: padding oracles, MAC comparisons and secret-dependent bignum operations.

The public surface is `include/mbedtls/constant_time.h` (`mbedtls_ct_memcmp`), `mbedtls_mpi_lt_mpi_ct` in `bignum.h`, and `bignum_core.h`.

Two gaps from this grep:
- **No call sites** in `ecp.c`, `aes.c` or `ecdsa.c`. Whatever constant-time protection ECC or AES has is implemented separately, or is absent. For P-256 the third-party `p256-m` has its own configuration symbol `MUL64_IS_CONSTANT_TIME` (`3rdparty/p256-m`), which suggests that code makes its own claim.
- Even inside the covered files, the facility only protects the operations that were rewritten to use it. Any remaining branch on a secret is outside its reach.