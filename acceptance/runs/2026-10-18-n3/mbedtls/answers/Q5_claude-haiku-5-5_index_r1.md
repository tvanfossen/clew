**Short answer:** Constant-time behaviour is not enforced by the compiler or by any build check. It is a discipline. Secret-dependent values are routed through a small set of branch-free helpers, and a set of Valgrind tests checks the result. On compilers or architectures without the hand-written assembly, the library falls back to plain C with no error and no guarantee beyond observation.

**1. What the instruction-level enforcement looks like**

The layer is `library/constant_time_internal.h` (declarations), `library/constant_time_impl.h` (static inline bodies) and `library/constant_time.c` (block operations). Secrets are held in an opaque `mbedtls_ct_condition_t` (all-ones or all-zeros mask). Selection is done with masks, not `if`:

- `mbedtls_ct_bool(x)` turns any non-zero value into an all-ones mask. On x86-64 it is `mov / neg / or / sar $63` (`constant_time_impl.h:157`). The AArch64, ARM and x86 variants are similar.
- `mbedtls_ct_if(c, a, b)` is `(c & a) | (~c & b)`, again in inline asm on the four supported targets.
- `mbedtls_ct_uint_lt` is a borrow-based subtraction with no flag-dependent branch.
- `mbedtls_ct_memcmp` XORs every byte into an accumulator and reads both buffers through `volatile` pointers. That stops the compiler from exiting early on the first difference (`constant_time.c:67`).

The compiler is kept from "seeing through" the values by `mbedtls_ct_compiler_opaque()`. With inline asm it is an empty `asm volatile("" : "+r"(x))` barrier. Without asm it XORs with a `volatile` global, `mbedtls_ct_zero` (`constant_time_impl.h:85`).

The `volatile` global, the barrier and the masking are all C-level. Nothing in the library controls the CPU's own timing (cache, division latency, speculation). The header says so: `mbedtls_ct_memcmp` "is not constant-time w.r.t. n".

**2. What happens on a compiler that cannot support it**

The asm path is selected by a chain of macros (`constant_time_impl.h:39-52`):

| Condition | Result |
|---|---|
| `MBEDTLS_HAVE_ASM` defined, GNU-compatible compiler, and arch is ARM / AArch64 / x86-64 / x86 | `MBEDTLS_CT_ASM` plus an arch-specific macro; hand-written asm for the primitives |
| `MBEDTLS_HAVE_ASM` defined, GNU-compatible, but other arch (RISC-V, MIPS, …) | `MBEDTLS_CT_ASM` set, so the opacity barrier is still asm, but the primitives are the C fallback |
| No asm (MSVC, IAR, armcc5, or `MBEDTLS_HAVE_ASM` commented out) | C fallback everywhere, `mbedtls_ct_zero` volatile global used for opacity |

Nothing fails to compile. The C fallback is only described as "observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h:55-59`). That is an empirical statement, not a guarantee. The one hard error is `check_config.h:250`: `MBEDTLS_HAS_MEMSAN` together with `MBEDTLS_HAVE_ASM` is `#error`, because MemorySanitizer cannot see through asm. So the MSan constant-flow build is forced onto the C path.

Two smaller points. `mbedtls_ct_memcmp` has a compile-time `#error` if `int` is narrower than 32 bits (`constant_time.c:99-105`). And the assembly is only as good as the asm for that arch: an incorrect register constraint would not be caught by the compiler, only by tests.

**3. How it is checked**

- The test helpers (`MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`, `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN`) are set by the components in `tests/scripts/components-sanitizers.sh` and `components-configuration-crypto.sh`. I did not read the marking code itself, so I can't confirm exactly how secrets are marked. The intent is that Valgrind memcheck reports any branch or address that depends on secret data.
- `test_with_valgrind_constant_time` (`components-configuration-crypto.sh:25`) runs every `tests/suites/*constant_time*.data` suite under memcheck and fails on any log output. `test_suite_constant_time_hmac` is excluded from that glob.
- Constant-flow components with `HAVE_ASM` disabled exist so the C fallback is exercised as well.

Nothing in the build enforces this for new code. A new module that branches on a secret compiles fine and passes unless a test exercises it under Valgrind.

**4. How far it reaches**

The public header `include/mbedtls/constant_time.h` exposes only `mbedtls_ct_memcmp`. Everything else is internal. In the library, the layer is used in 27 files, with roughly 140 call sites outside the ct files themselves (my estimate from grep counts). Representative users, from the `mbedtls_ct_memcmp` call sites:

| Area | Files | Use |
|---|---|---|
| AEAD tag checks | `gcm.c`, `ccm.c`, `chachapoly.c`, `cipher.c`, `psa_crypto_driver_wrappers.h`, `psa_crypto_mac.c` | tag comparison |
| MAC / key-wrap | `psa_crypto.c`, `nist_kw.c` | MAC and ICV comparison |
| RSA | `rsa.c` | PKCS#1 v1.5 padding checks, signature verification, and `mbedtls_ct_memmove_left` on decrypt |
| TLS | `ssl_msg.c` (record MAC, `memcpy_offset`), `ssl_tls12_client/server.c`, `ssl_tls13_*.c`, `ssl_cookie.c`, `ssl_tls.c` | Finished/verify_data, PSK identity, binder, cookie, and record-MAC comparisons |
| Bignum | `bignum_core.c`, `bignum.c`, `bignum_mod_raw.c`, `bignum_mod.c` | comparisons, zero checks, gcd/modinv |
| Other | `base64.c` | decoding table lookups |

The coverage is wide. Where it stops is the caveat above: a module that is not explicitly converted to these helpers is not covered by the facility, and nothing in the build flags the gap. Protecting the rest of the library is a review problem, not a compiler one.

Caveats on this answer: I read the helper headers, the constant-time source, the asm variants and the test components. I did not run the Valgrind suites or inspect the generated assembly for any target. The "roughly 140" call-site figure is from grep counts and may be off by a few.