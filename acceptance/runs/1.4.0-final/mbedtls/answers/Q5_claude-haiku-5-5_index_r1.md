## Short answer

Constant time in Mbed TLS is a **discipline plus a small set of primitives**, not a compiler-enforced property. The primitives are in `library/constant_time_impl.h`. On GCC/Clang builds with `MBEDTLS_HAVE_ASM` on a supported architecture, the critical "make a mask" and "select" steps are hand-written inline assembly, and an empty `asm volatile` barrier hides values from the optimizer. On anything else, the code falls back to plain C that is only *observed* to stay branch-free. Nothing in the build rejects an unsupported compiler. The facility reaches into roughly 29 library files, but it is not uniform across the library.

## How it is enforced at the instruction level

**1. Opaque values.** `mbedtls_ct_condition_t` is an unsigned integer that is only ever 0 or all-ones. `MBEDTLS_CT_TRUE`/`MBEDTLS_CT_FALSE` are produced through `mbedtls_ct_compiler_opaque()` (`constant_time_impl.h:85`). On the assembly path that is `asm volatile("" : [x] "+r"(x))`, a no-op the optimizer cannot see through, so it cannot prove the value at compile time and cannot turn a select back into a branch.

**2. Mask generation.** `mbedtls_ct_bool(x)` (`constant_time_impl.h:120`) turns any nonzero value into all-ones with no branch. Each architecture has its own asm, for example x86-64 `mov/neg/or/sar $63`, AArch64 `neg/orr/asr`, and ARM `negs/orrs/asrs`.

**3. Selection and comparison.** `mbedtls_ct_if` (`:205`) is a masked select: `(if1 & c) | (if0 & ~c)`, again in asm on the supported targets. The comparisons (`uint_lt`, `uint_ge`, `uint_eq`, …) are built on the mask. For example, `uint_ge` is `~uint_lt` (`:501`).

**4. Memory operations.** `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers so the compiler must read every byte and cannot exit early. It ORs the XORs and returns a non-zero value only if the accumulator is non-zero. The `mbedtls_ct_memcpy_if`, `mbedtls_ct_memcpy_offset` and `mbedtls_ct_zeroize_if` helpers always touch every byte, so the access pattern does not depend on the secret.

## What happens on a compiler or target that cannot support it

The selection is in the `#if` cascade at `constant_time_impl.h:40–52`:

| Condition | Result |
|---|---|
| `MBEDTLS_HAVE_ASM` and `__GNUC__` (GCC or Clang, not old armcc) | `MBEDTLS_CT_ASM` is defined. Architecture macros are added only for ARM/Thumb, AArch64, x86-64 and i386. |
| `MBEDTLS_CT_ASM` but another architecture (e.g. RISC-V with GCC) | The opaque barrier is still asm, but `mbedtls_ct_bool` and `mbedtls_ct_if` use the plain-C fallback. |
| No `MBEDTLS_HAVE_ASM`, or a non-GNU compiler such as MSVC | `mbedtls_ct_compiler_opaque` returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a global `volatile` zero (`constant_time.c:29`). The plain-C `mbedtls_ct_bool` uses arithmetic (`-xo | -(xo>>1)`, then a sign-bit extract) written so it does not compile to branches. |

The comment at `constant_time_internal.h:55–59` says the C fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023." That is an observation about specific compiler versions, not a guarantee. A future optimizer could still turn the C path into a branch, and nothing in the build detects that. The code only checks one thing at compile time: a 16-bit `int` platform gets an `#error` in `mbedtls_ct_memcmp`. Unsupported compilers do not fail the build. They silently get the weaker path.

## How it is checked

The enforcement is mostly testing, not compilation:

- `tests/suites/test_suite_constant_time*.function` wraps secret inputs in `TEST_CF_SECRET` so MSan or Valgrind flags any secret-dependent branch or address.
- `tests/scripts/components-configuration-crypto.sh:25` (`test_with_valgrind_constant_time`) runs the `*constant_time*` suites under Valgrind memcheck. The HMAC suite is excluded, and the run fails if the log is non-empty.
- `3rdparty/p256-m` uses its own `CT_POISON`/`CT_UNPOISON` macros around `VALGRIND_MAKE_MEM_UNDEFINED`.

I did not build any of these or run Valgrind here, so I have not verified that they pass on this checkout.

## How far it reaches

Counting `mbedtls_ct_\w+(` occurrences in `library/` gives 286 across 29 files. The main users are:

- **TLS record and handshake:** `ssl_msg.c` (CBC padding and MAC check), `ssl_tls.c`, `ssl_tls12_server.c`, `ssl_tls13_*`, `ssl_cookie.c`, and the Finished and binder comparisons.
- **AEAD and MAC tag checks:** `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `nist_kw.c`, `psa_crypto_mac.c`, and the PSA driver wrappers.
- **Padding:** `cipher.c` (`mbedtls_get_pkcs_padding`) and `base64.c`.
- **RSA:** `rsa.c` for PKCS#1 v1.5 and OAEP unpadding, using `mbedtls_ct_zeroize_if` and `mbedtls_ct_memcmp`.
- **Bignum:** `bignum_core.c` has `mbedtls_mpi_core_lt_ct`, `check_zero_ct`, a constant-time GCD/modinv, and `exp_mod_optionally_safe`. That function takes an `E_public` flag, so the exponent is only protected when the caller says it is secret.

Gaps I found or could not rule out:

- **ECC:** `ecp.c` and `ecdsa.c` call `mbedtls_mpi_gcd_modinv_odd` and `mbedtls_mpi_exp_mod`. They do not call `mbedtls_ct_*` directly, so ECC point arithmetic is protected only as far as the bignum layer is. I did not audit ECC scalar multiplication. The constant-time claim there rests on the bignum core and on the separate `p256-m` code.
- **Scope of the guarantee:** `mbedtls_ct_memcmp` is constant time only with respect to the data and the outcome, not the length `n`. The documentation says so explicitly.
- **AES and Camellia:** these files contain `_ct`-style references (9 and 3 matches). I did not check whether those are constant-time table-free implementations or something else.

## Summary

Enforcement is by convention plus tests. Assembly barriers and masks give real protection on GCC/Clang for the listed architectures. Everywhere else the library relies on a C fallback whose safety is an observed property, and nothing in the build flags the weaker path. The facility is used throughout TLS, AEAD tag checks, RSA unpadding and bignum core. ECC scalar multiplication and some other layers rely on it only indirectly, and I did not verify those.