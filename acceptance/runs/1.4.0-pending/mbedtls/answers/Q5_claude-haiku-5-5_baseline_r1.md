## Short answer

Constant-time behaviour in mbedtls is a best-effort discipline, not a guarantee. A small module, `library/constant_time_impl.h` (plus `library/constant_time.c` and the public `include/mbedtls/constant_time.h`), builds branch-free primitives. On a few architectures these are hand-written assembly. Everywhere else they are plain C that is *believed* to compile branch-free. Nothing in the build checks the generated code, and the project says so: `SECURITY.md` states the protection is "limited" and that "compilers can introduce timing side channels… this prevention may not be complete."

## How it works at the instruction level

1. **Secret values are masks, not booleans.** `mbedtls_ct_condition_t` is an all-ones or all-zeros word (`size_t`, `uint64_t` or `uint32_t`, chosen by pointer and MPI width; `constant_time_internal.h`). `mbedtls_ct_bool(x)` turns any nonzero `x` into that mask with no branch. `mbedtls_ct_if(c, a, b)` is `(c & a) | (~c & b)`.

2. **The optimizer is kept from reasoning about values.** `mbedtls_ct_compiler_opaque(x)` is `asm volatile("" : "+r"(x))` when assembly is enabled. Otherwise it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` zero the compiler cannot fold. This stops the compiler from proving a value and turning the mask arithmetic back into a `cmp`/`jcc`.

3. **Some primitives are pinned in assembly.** `mbedtls_ct_bool`, `mbedtls_ct_if`, and `mbedtls_ct_uint_lt` have hand-written sequences for AArch64, 32-bit ARM/Thumb, x86-64 and x86-32. The asm is used only when `MBEDTLS_HAVE_ASM` is defined, the compiler is GNU-compatible, and the architecture and word size match. For example, the x86-32 path is taken only when the type is 32-bit.

4. **Memory operations are volatile and read everything.** `mbedtls_ct_memcmp` reads every byte through `volatile` pointers, XORs into an accumulator, and has no early exit. The comment says this avoids a compiler-introduced early-out. The `mbedtls_ct_memcpy_if`, `_memmove_left` and `_zeroize_if` helpers do the same for secret-dependent copies.

## What happens on a compiler that cannot support it

There is no compile error and no warning. The code degrades silently to the C fallback:

| Situation | Result |
|---|---|
| `MBEDTLS_HAVE_ASM` undefined (user config, `component_test_m32_no_asm`) | All primitives use C; `mbedtls_ct_zero` is used as the opaque barrier |
| Not GNU-compatible (MSVC, old ARMCC) | `MBEDTLS_CT_ASM` is not defined; C fallback |
| GNU-compatible but unlisted architecture | `MBEDTLS_CT_ASM` set, but each primitive's `#else` branch runs C code |
| 32-bit x86 with 64-bit MPI limbs | Word size doesn't match the x86 asm guard; C fallback |

The C fallback's comment says it was "observed to be constant-time" on recent gcc, clang and MSVC as of May 2023. That is an empirical observation, not a proof, and it can change with a compiler upgrade or a different `-O` level. `SECURITY.md` also says the project treats exploitable side channels as vulnerabilities at `-O2`/`-Os` on common compilers, and gives `-O3`/`-Oz` less scrutiny.

So on an unsupported toolchain, the assurance you get is the C fallback's behaviour under that compiler, and the library does not report that it has dropped to it.

## How far it reaches

About 400 `mbedtls_ct_*` references across roughly 22 library files. Only `mbedtls_ct_memcmp` is public. The rest is internal.

| Area | Where the facility is used |
|---|---|
| RSA PKCS#1 v1.5 and OAEP unpadding | `rsa.c` (37 uses), including padding-validity and output-size checks |
| Bignum | `bignum_core.c`, `bignum.c`, `bignum_mod_raw.c`: conditional assign/swap, `uint_le_mpi` |
| TLS record decryption (CBC) | `ssl_msg.c` (24 uses): padding verification, MAC computed over the full buffer with `ct_hmac`, `memcpy_if` to pick the MAC input without a secret-dependent branch |
| Symmetric ciphers and padding | `cipher.c` (30), `psa_crypto_cipher.c`, `psa_crypto.c` |
| Tag and MAC comparison | `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `nist_kw.c` (`ct_memcmp_partial`) |
| Base64 decoding | `base64.c` (21) |
| TLS handshake | `ssl_tls.c`, `ssl_tls12_*`, `ssl_tls13_*`, `ssl_cookie.c` |

Two gaps to note:

- **ECP** (`ecp.c`) does not call `mbedtls_ct_*` directly. It uses bignum-level `mbedtls_mpi_safe_cond_assign`/`_swap` for the scalar-dependent selections. I did not verify that its comb-table lookup (`ecp_select_comb`) is constant-time.
- **Lengths and public values are not covered.** `mbedtls_ct_memcmp` is documented as "not constant-time w.r.t. `n`". Anything the code treats as public is out of scope.

## How it is verified

- Test suites are annotated with `TEST_CF_SECRET` and `TEST_CF_PUBLIC`: `constant_time`, `constant_time_hmac`, `bignum`, `bignum_core`, `bignum_mod_raw`, `cipher`, `pkcs1_v15`, `ssl`, `base64`, `psa_crypto_constant_time`.
- Under `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (memcheck) or `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` (MemorySanitizer), the secret is marked uninitialized. A secret-dependent branch or memory address then shows up as a report.
- CI runs this in `components-sanitizers.sh`, including a no-asm build (`component_release_test_valgrind_constant_flow_no_asm`) and an asm build (`valgrind asm constant_time`).

Limits of this check:

- The macro definitions live in the `framework` submodule, which is empty in this checkout. I could read the callers but not the definitions, so I did not verify exactly what `TEST_CF_SECRET` does.
- It only exercises the paths the tests reach, and only on the compilers and flags CI uses.

I did not build or run any tests here; this is from reading the source.