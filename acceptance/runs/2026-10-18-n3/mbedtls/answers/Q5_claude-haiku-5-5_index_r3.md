## Short answer

Constant-time behaviour in mbedtls is a design discipline plus a small set of hand-written primitives, not something the build verifies. The primitives are branch-free C, backed by inline assembly on four architecture families. On anything else the code silently falls back to plain C. The only checks are dynamic: Valgrind and MemorySanitizer runs of dedicated test suites, and those are opt-in.

## How it is enforced at the instruction level

The core is `library/constant_time_impl.h` and `library/constant_time_internal.h`. Secrets are held in an opaque `mbedtls_ct_condition_t` (all-ones or all-zeros mask) and manipulated only through `mbedtls_ct_*` operations.

- **Opaque values.** `mbedtls_ct_compiler_opaque()` (`constant_time_impl.h:85`) stops the optimiser from learning a value. With asm it is an empty `asm volatile("" : "+r"(x))` barrier. Without asm it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global set to 0 (`constant_time.c:29`).
- **Masks without branches.** `mbedtls_ct_bool()` (`constant_time_impl.h:120`) turns a value into a mask with `neg / or / asr` on Arm, AArch64 and x86. Selection (`mbedtls_ct_if`, line 205) is `and / not / and / or`. Comparison (`mbedtls_ct_uint_lt`, line 271) is a sub-and-sign-bit trick.
- **Memory operations read everything.** `mbedtls_ct_memcmp` (`constant_time.c:67`) reads every byte through `volatile` pointers and ORs the differences, so there is no early exit. `mbedtls_ct_memcpy_if` (line 169) always reads both sources and blends them with masks. `mbedtls_ct_memcpy_offset` (line 214) scans every candidate offset.

Assembly is used only when `MBEDTLS_HAVE_ASM` is defined (on by default, `mbedtls_config.h:52`), the compiler is GCC-compatible (`__GNUC__`, which includes clang), and the target matches one of four families: Arm 32-bit/Thumb, AArch64, x86-64, or i386 (`constant_time_impl.h:40-51`).

## What happens on a compiler or target that cannot support it

There is no `#error` and no warning for the ordinary cases. The code drops to the C path:

| Situation | Result |
|---|---|
| `MBEDTLS_HAVE_ASM` undefined, MSVC, ARMCC 5 | `MBEDTLS_CT_ASM` undefined. Opaque barrier is the volatile-XOR, and all operations are portable C. |
| GCC/clang with asm on an unlisted arch (e.g. RISC-V, MIPS) | `MBEDTLS_CT_ASM` is defined but no arch branch matches. Opaque is the empty-asm barrier, and operations are the portable C arithmetic. |
| Pointer size or word size outside the asm branches | Same C fallback, with `mbedtls_ct_memcmp` using a byte loop. |

The 32-bit word fast paths in `constant_time.c` are gated on ARM or AArch64 with efficient unaligned access, so other targets get a byte loop. The only hard `#error`s are for an `int` narrower than 32 bits (`constant_time.c:105`) and for an unsupported unaligned-volatile config (`constant_time.c:60`).

The header's own claim is that the C fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h:55-59`). That is an observation about specific compiler versions, not a guarantee.

## How far it reaches

The public surface is one function, `mbedtls_ct_memcmp` (`include/mbedtls/constant_time.h:32`). Everything else is internal. The internal primitives appear about 396 times across 29 library files. The main consumers I confirmed:

- **TLS record layer** (`library/ssl_msg.c`): constant-time HMAC over secret-length data (`mbedtls_ct_hmac`, lines 66 and 187), CBC padding checks (lines 1916–1978), MAC compare (lines 1798 and 2071).
- **TLS 1.2 server** (`library/ssl_tls12_server.c:3409-3474`): premaster-secret validity check, with a constant-time substitution of a fake premaster secret.
- **CBC padding and tag compares** (`library/cipher.c:861-998`, 1298, 1319): padding removal and tag comparison.
- **RSA PKCS#1 v1.5 unpadding** (`library/rsa.c:420`): compiled only when `MBEDTLS_RSA_ALT` is off.
- **Bignum** (`library/bignum_core.c`, `bignum.c`, `bignum_mod_raw.c`): conditional assign/swap, `lt_ct`, and a constant-time binary GCD for modular inverse (`bignum_core.c:1181-1233`).
- **ECC** (`library/ecp.c:1202-1215`, `2143`): point-multiplication selection goes through `mbedtls_mpi_safe_cond_assign`, which inherits the bignum primitives.
- **PSA** (`library/psa_crypto.c`): hash and MAC compares, and status masking on output length (around 4703 and 4857).
- **Other**: `base64.c` (21 uses), `nist_kw.c`, `ccm.c`, `gcm.c`, `chachapoly.c`, `cmac.c`.

Two gaps I did not verify. I did not check whether table-based ciphers such as AES avoid secret-indexed lookups, so I cannot say whether cache-timing is covered. The vendored `3rdparty/p256-m` has its own `MUL64_IS_CONSTANT_TIME` config and does not appear to use this facility.

## How it is tested

Nothing checks this at build time. The enforcement is dynamic:

- `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25-33`) runs the `*constant_time*.data` suites under `valgrind --tool=memcheck`.
- `components-sanitizers.sh` runs the same idea under MemorySanitizer.
- Both depend on `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` / `_MEMSAN` (`mbedtls_config.h:2109-2142`), which are commented out by default and explicitly not part of the API.
- The suites (`tests/suites/test_suite_constant_time.function`) say they are built so that a non-constant-time implementation shows up under MSan or Valgrind.

The `test/constant_flow.h` helper that does the secret marking is not in this checkout (a Glob for it found nothing), so I could not read the poisoning code itself. The mechanism is inferred from the config comments and the suite header.

The practical limit: a secret-dependent branch is only caught if a test drives that path with the flags on. Coverage is whatever the dedicated suites exercise.