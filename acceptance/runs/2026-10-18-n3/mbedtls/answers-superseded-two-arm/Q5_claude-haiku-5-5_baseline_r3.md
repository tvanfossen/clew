## Short answer

Constant-time behaviour in Mbed TLS is a convention backed by a small primitive layer, inline asm on a few architectures, and Valgrind/MemorySanitizer tests. Nothing enforces it at the type level, and on a compiler without asm the library silently falls back to plain C with weaker guarantees.

## How it is enforced at the instruction level

The core is `library/constant_time_internal.h` (declarations and the design contract) and `library/constant_time_impl.h` (inline definitions), with `library/constant_time.c` for the non-inline pieces.

- **Secrets are never branched on.** Secret conditions use `mbedtls_ct_condition_t`, which is a plain unsigned integer typedef (`uint32_t`/`uint64_t`/`size_t`). The header says it "must be treated as opaque", but C will still let you write `if (cond)`. Only review and tests stop that.
- **Conditions are full-width masks.** `mbedtls_ct_bool(x)` turns any non-zero value into all-ones or all-zeros using `neg`/`orr`/`asr` (AArch64, ARM), `mov`/`neg`/`or`/`sar` (x86-64), or the same idea in 32-bit forms. Equality, comparison, `_if` selects, `_memcpy_if` and similar operations are built from masks and bitwise ops.
- **`mbedtls_ct_compiler_opaque()` hides values from the optimiser.** With asm it is an empty `asm volatile("" : "+r"(x))`. Without asm it XORs with `mbedtls_ct_zero`, a `volatile` global holding 0. The compiler cannot prove the value, so it cannot turn a mask back into a branch.
- **Memory reads are forced to completion.** `mbedtls_ct_memcmp()` casts both buffers to `volatile` and ORs all differences together, so it cannot exit early. Where the target allows it, it uses unaligned `volatile` loads written in asm (`mbedtls_get_unaligned_volatile_uint32`).

The asm path is selected by `MBEDTLS_CT_ASM`, which is defined only when all of these hold (`constant_time_impl.h` lines ~37–52):

- `MBEDTLS_HAVE_ASM` is defined. It is on by default in `include/mbedtls/mbedtls_config.h`.
- The compiler is GNU-compatible (GCC or Clang). armcc5 is excluded.
- The target is ARM/Thumb, AArch64, x86-64 or i386.

## What happens on a compiler that cannot support it

There is no build error and no warning. If any condition above fails, `MBEDTLS_CT_ASM` stays undefined and the plain C versions are compiled. Those rely on arithmetic tricks that the comment says were observed to produce branch-free code on "latest gcc, clang and MSVC as of May 2023". That is an observation about compiler behaviour, not a guarantee.

Two cases are worth knowing about:

- **MSan builds cannot use asm.** `check_config.h` lines 250–251 raise `#error` if `MBEDTLS_HAVE_ASM` is set together with MemorySanitizer. Sanitizer builds therefore always test the C fallback.
- **The asm path is tested separately.** `tests/scripts/components-sanitizers.sh` has a comment that under Valgrind or MSan the plain C path runs by default, and a separate step runs `test_suite_constant_time` against the asm path.

## How it is verified

- `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` and `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` (`mbedtls_config.h` ~2109–2142) are opt-in, extended-testing switches. The test macros (`TEST_CF_SECRET` and related) are supposed to mark secret inputs as uninitialised. Any branch or memory index that depends on them then shows up as an uninitialised-value report.
- CI components: `component_release_test_valgrind_constant_flow`, `component_test_memsan_constant_flow` and `component_test_memsan_constant_flow_psa`. The Valgrind one skips suites that have no `TEST_CF_` annotations.
- Caveat: those annotation macros live in the `framework` submodule. That directory is empty in this checkout, so I could not read the macros themselves.
- Some suites check op-count invariants instead. The ECP self-test has "constant op_count" cases.

## How far it reaches

Usage counts of `mbedtls_ct_*` per file, from `library/`:

| Area | Files (approx. uses) | What is protected |
|---|---|---|
| RSA | `rsa.c` (37) | PKCS#1 v1.5 unpadding, `mbedtls_ct_rsaes_pkcs1_v15_unpadding` |
| Bignum | `bignum_core.c` (32), `bignum.c` (26), `bignum_mod_raw.c` | Core limb operations used by RSA and ECP |
| Block cipher modes | `cipher.c` (30) | CBC padding removal |
| TLS record layer | `ssl_msg.c` (24), `ssl_tls.c`, `ssl_tls12_server.c` (8), `ssl_tls12_client.c` | CBC padding and MAC check, `mbedtls_ct_hmac`, `mbedtls_ct_memcmp` on the record MAC |
| Encoding | `base64.c` (21) | Decoding without data-dependent branches |
| Key wrap / AEAD / MAC | `nist_kw.c` (4), `ccm.c`, `gcm.c`, `cmac.c`, `chachapoly.c` | Tag and partial comparisons |
| PSA | `psa_crypto.c` (9), `psa_crypto_cipher.c`, `psa_crypto_mac.c`, `psa_crypto_driver_wrappers.h` | Forwarding of the above |
| Cookies | `ssl_cookie.c` | Cookie comparison |

ECP is different. `ecp.c` has no direct `mbedtls_ct_*` calls. It uses `mbedtls_mpi_safe_cond_assign/neg/swap` through its `MPI_ECP_COND_*` macros. `ecp_select_comb()` reads the whole precomputed table to resist cache-timing attacks. Some ECP functions are explicitly marked "NOT constant-time" (`ecp.c` ~2734, 2769, 2873), so the constant-time guarantee is per function, not per module.

`3rdparty/p256-m` is a separate, self-contained P-256 implementation that is designed to be constant-time on its own terms.

`SECURITY.md` (line ~109) says it plainly: compilers can still introduce timing side channels, and the countermeasures "may not be complete" across compilers, options and platforms.

## Bottom line

Constant-time is a discipline the code follows, not something the compiler guarantees. The asm barriers and masks are what keep the optimiser honest on GCC/Clang for ARM, AArch64 and x86. Everywhere else you are relying on the C fallback's behaviour with your particular compiler. The Valgrind/MSan tests catch regressions in the flow, but they only cover functions that carry `TEST_CF_` annotations, and I could not inspect those macros here.