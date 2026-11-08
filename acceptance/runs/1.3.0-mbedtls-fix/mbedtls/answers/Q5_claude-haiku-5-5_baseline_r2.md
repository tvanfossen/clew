Short answer: the guarantee is enforced by hand-written inline assembly for a few architectures, plus a plain-C fallback that is only believed to be constant-time. Nothing checks the generated code. The facility is used in the bignum, RSA, cipher/MAC, AEAD and TLS record paths, but it is not applied everywhere. I read the source and did not build or run anything.

**How it is enforced at the instruction level**

- The primitives live in `library/constant_time_impl.h` and are built on a small set of operations: `mbedtls_ct_bool` turns any non-zero value into an all-ones mask, `mbedtls_ct_if` does a mask-based select, and comparisons are built from subtraction and sign bits. Results are masks (`mbedtls_ct_condition_t`), not C booleans, so callers never branch on them.
- On GCC/Clang-style compilers, `MBEDTLS_CT_ASM` is defined when `MBEDTLS_HAVE_ASM` is on (it is by default, `include/mbedtls/mbedtls_config.h:52`). Hand-written asm exists for ARM 32-bit (including Thumb), AArch64, x86-64 and x86-32. Each variant is gated on the matching word size, so for example 32-bit x86 with a 64-bit `mbedtls_ct_uint_t` falls through to C.
- The asm does two jobs. The arithmetic sequences avoid branches and conditional instructions. `mbedtls_ct_compiler_opaque()` is an empty `asm volatile` with a `+r` constraint, which stops the optimiser from knowing the value.
- A plain-C fallback is used everywhere else. It is opaque in the same way: it XORs with `volatile mbedtls_ct_zero`, which the compiler cannot prove is 0. The source says the C version "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an observation, not a proof.
- Two helpers are not pure arithmetic. `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers so it cannot exit early (`library/constant_time.c`). `mbedtls_ct_memcpy_if` and `mbedtls_ct_memcpy_offset` do a masked copy over the whole range, so the memory access pattern does not depend on the secret.

**What happens on a compiler that cannot support it**

- The asm gate is `defined(__GNUC__) && (!defined(__ARMCC_VERSION) || __ARMCC_VERSION >= 6000000)`. MSVC, IAR, old armcc, and anything that is not GNU-compatible silently get the C fallback.
- Architectures without an asm variant also get the C fallback. Disabling asm (commenting out `MBEDTLS_HAVE_ASM`) takes the same path.
- There is no `#error` or warning for either case. The only related guards are for `int` narrower than 32 bits in `mbedtls_ct_memcmp`, and for MemorySanitizer combined with asm.
- So on those targets the guarantee degrades from "asm sequence, checked by instruction review" to "C code that the optimiser might still branch on". The library does not tell you which path you got.

**How far it reaches**

Call counts from `grep -c mbedtls_ct_` on the library sources:

| Area | Files (count) | What it protects |
|---|---|---|
| Bignum | `bignum_core.c` (32), `bignum.c` (26), `bignum_mod_raw.c` (2) | Conditional assign/swap, comparisons on secret values |
| RSA | `rsa.c` (37) | PKCS#1 v1.5 unpadding, with errors folded into a mask so the timing does not leak which error occurred |
| Cipher/MAC | `cipher.c` (30), `cmac.c`, `ccm.c`, `gcm.c`, `chachapoly.c`, `nist_kw.c` (4) | CBC padding removal, tag comparison |
| TLS | `ssl_msg.c` (24), `ssl_tls12_server.c` (8), `ssl_tls12_client.c`, `ssl_tls13_server.c`, `ssl_tls.c`, `ssl_cookie.c` | Record MAC check via `mbedtls_ct_hmac`, Finished-message compare, premaster length check |
| PSA | `psa_crypto.c` (9), `psa_crypto_cipher.c` (4), `psa_crypto_mac.c` | Hash and MAC compare |
| Other | `base64.c` (21), `ecp_curves.c` | Base64 decode, conditional reduction |

Limits I found:

- ECC point arithmetic in `ecp.c` mostly goes through `mbedtls_mpi_safe_cond_assign`/`_swap` wrappers over the bignum layer, not directly through `mbedtls_ct_`. Some functions are explicitly marked "NOT constant-time" (`ecp.c:2734`, `2769`, `2873`) and are only used for public data.
- `aes.c` does not use the `mbedtls_ct_` API according to the grep. I did not check whether its table lookups are cache-timing safe, so I am not making a claim about AES.
- `ChangeLog` says RSA PKCS#1 v1.5 decryption is "inherently dangerous" even with the constant-time error handling.

**How it is verified**

- Constant-flow testing marks secret inputs with `TEST_CF_SECRET` and public outputs with `TEST_CF_PUBLIC`. Valgrind memcheck then reports any branch or address that depends on a secret. This is `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (`include/mbedtls/mbedtls_config.h:2126`), run by `component_release_test_valgrind_constant_flow` on `*constant_time*.data` suites.
- The MemorySanitizer variant (`MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN`) requires building with clang MSan and turning off asm. `check_config.h:250` makes it an error to combine MSan with asm.
- The result is that the asm path is never exercised by MSan, and the C fallback is what gets tested under MSan. Testing is also limited to the platforms and compilers the CI runs.
- The `TEST_CF_*` macros are defined in the `framework` submodule, which is not checked out in this repository. I could not read their definitions, so my description of them comes from the comments in the test suites.

**Bottom line:** the asm is the only real instruction-level guarantee, and it covers the main ARM and x86 targets under GCC or Clang. Everywhere else the library relies on a C fallback that is not verified at the instruction level and is not flagged at build time. The consumers listed above, mainly RSA, the TLS record path, and the cipher/MAC compares, are the ones where the facility matters most.