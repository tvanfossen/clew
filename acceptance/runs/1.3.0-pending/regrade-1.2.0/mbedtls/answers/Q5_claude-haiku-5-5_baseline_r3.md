Constant-time behaviour in mbedtls is achieved by construction, not proven. The library builds secret-dependent logic from mask arithmetic, and a few hand-written assembly primitives pin the compiler's output on common targets. Tests then check the result dynamically. The repo's own SECURITY.md says the protection is limited.

**1. How it is enforced at the instruction level**

Everything lives in `library/constant_time_impl.h` (types and inline primitives) and `library/constant_time.c` (block operations). Secrets are represented as all-ones or all-zeros masks (`mbedtls_ct_condition_t`), and every operation is a bitwise expression on them:

- **Hiding values from the optimiser.** `mbedtls_ct_compiler_opaque()` is an empty `asm volatile` barrier when assembly is available. Otherwise it XORs with a `volatile` global that is zero, so the compiler cannot prove the value.
- **Mask primitives in asm.** `mbedtls_ct_bool` (zero-or-nonzero to mask), `mbedtls_ct_if` (select) and `mbedtls_ct_uint_lt` (borrow-based compare) have hand-written asm for 32-bit Arm/Thumb, AArch64, x86 and x86-64. The asm is the only thing guaranteeing no `jcc`, `csel` or similar gets emitted.
- **Block operations.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers, so it cannot exit early, and ORs the XOR of every byte. `mbedtls_ct_memcpy_if` and `mbedtls_ct_memcpy_offset` copy by mask over every candidate offset. `mbedtls_ct_memmove_left` is a fixed-count shift network.

**2. A compiler or target that cannot support it**

Asm is used only when all of these hold: `MBEDTLS_HAVE_ASM` is defined, the compiler is GNU-compatible (`__GNUC__`, which includes clang), it is not armcc5, and the target is one of the four listed architectures. Anything else falls back to plain C. Specifically:

| Situation | What happens |
|---|---|
| MSVC, IAR, armcc5 | Pure C fallback, no build error or warning |
| `MBEDTLS_HAVE_ASM` commented out | Pure C fallback even on GCC |
| GNU compiler on an unlisted arch (RISC-V, PowerPC, MIPS…) | `MBEDTLS_CT_ASM` is defined, so the opaque barrier is asm, but `bool`, `if` and `lt` use the C fallback |

The C fallback relies on the compiler not turning the arithmetic back into a branch. The code comment says this was "observed to be constant-time on latest gcc, clang and MSVC as of May 2023", which is an observation rather than a guarantee. Degradation is silent. The only hard `#error` in this area concerns `int` width, not timing. SECURITY.md says it plainly: compiler-induced timing channels may not be fully prevented, and guarantees attach to common `-O2`/`-Os` builds. `-O3` and `-Oz` are "less scrutinized."

**3. Verification**

Verification is dynamic and per-path. Test suites under `tests/suites/*constant_time*` mark secret inputs with `TEST_CF_SECRET` and public ones with `TEST_CF_PUBLIC`. With `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` (clang MemorySanitizer) or `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (memcheck), a branch or address that depends on a secret is reported. CI runs these in `tests/scripts/components-sanitizers.sh` and `components-configuration-crypto.sh`. The helper header `test/constant_flow.h` lives in the `framework` submodule, which is an empty gitlink in this checkout, so I could not read its mechanism. Tests only cover the paths they exercise, on the compiler and flags they are built with.

**4. How far it reaches**

The primitives are used in about 20 library files. Counts from grep: `rsa.c` 37, `bignum_core.c` 32, `cipher.c` 30, `bignum.c` 26, `ssl_msg.c` 24, `base64.c` 21, `psa_crypto.c` 9, `ssl_tls12_server.c` 8.

- **RSA:** PKCS#1 v1.5 unpadding (`rsa.c` ~420) and OAEP decode (~2040) run to completion and fold errors into masks. Signature comparisons use `mbedtls_ct_memcmp`.
- **CBC padding:** `cipher.c` ~861 checks and strips padding without an early exit.
- **TLS record MAC:** `ssl_msg.c` uses `mbedtls_ct_hmac` (~66, ~187) and a constant-time MAC compare (~1798).
- **ECC:** `ecp.c` scalar multiplication uses `mbedtls_mpi_safe_cond_assign`/`swap` (~1202–1215), backed by `bignum_core` table lookups.

Limits are explicit in SECURITY.md:

- Timing protection is "limited" and aimed at publicly documented attacks. The library is "moving towards" timing-invariant code but has not reached it.
- Block-cipher timing (table-based AES) is not fully covered, and the docs flag it as a warning.
- Local non-timing side channels (power, EM) and fault injection get no guarantees.
- Lengths and public sizes leak by design. `mbedtls_ct_memcmp` is explicitly "not constant-time w.r.t. `n`".
- The PSA transition doc says there is no PSA equivalent, so `constant_time.h` remains the only tool for this.

I read the code and CI definitions but did not build or run the tests, since the framework submodule is missing from this checkout.