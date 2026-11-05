## Short answer

Constant-time behavior in mbedtls is a convention enforced by hand-written inline assembly and an opaque-value barrier, not by the compiler. Verification is dynamic: memcheck and MSan flag branches on secret data in CI. On compilers or architectures without the asm path, the code silently falls back to plain C, which the project describes as only observed to be constant-time. The facility reaches the places that handle secrets in the TLS record layer, padding checks, tag comparisons and bignum internals. It does not cover everything: several secret-handling modules call no `mbedtls_ct_` function at all. I read the source only; I did not build or run the test components.

## How it is enforced at the instruction level

The API is `library/constant_time_internal.h` and `library/constant_time_impl.h`, with a small public wrapper in `include/mbedtls/constant_time.h`. Three mechanisms do the work:

1. **Hand-written asm for the primitives.** `mbedtls_ct_bool()`, `mbedtls_ct_if()` and the comparison routines are fixed instruction sequences. On AArch64 (`constant_time_impl.h:130`), `mbedtls_ct_bool` is `neg` / `orr` / `asr 63`, which builds an all-ones or all-zeros mask with no branch. Selection is `and` and `eor` masking (`:209`, `:273`). x86-64 and 32-bit ARM and x86 have equivalent sequences.
2. **An opaque barrier.** `mbedtls_ct_compiler_opaque()` (`:85-92`) is `asm volatile("" : [x] "+r"(x))`. The compiler must treat the output as an unknown register value, so it cannot constant-fold a secret condition or rewrite the mask arithmetic into a branch. The header states the contract: the compiler "should never be able to prove anything about its value at compile-time" (`constant_time_internal.h`, top comment).
3. **Opaque types.** `mbedtls_ct_condition_t` is an all-ones or all-zeros word. Callers combine conditions with `bool_and`, `bool_or` and `if`, never with `if (secret)`.

Two limits matter here. The barrier stops the compiler from *knowing* the value, not from emitting a branch elsewhere in the caller. Any `if (secret)` written outside this API still branches. The guarantee holds only where callers use the API.

## What happens on a compiler that cannot support it

The asm path requires `MBEDTLS_HAVE_ASM` plus a GNU-compatible compiler with extended asm (`constant_time_impl.h:39-52`). Otherwise `MBEDTLS_CT_ASM` stays undefined and the library uses C fallbacks:

- `mbedtls_ct_zero` becomes `volatile mbedtls_ct_uint_t = 0` (`constant_time.c:23-27`), and the opaque barrier becomes `x ^ mbedtls_ct_zero`.
- Masks come from arithmetic such as `-xo | -(xo >> 1)` and a sign-bit extraction (`impl.h:183-202`).
- Selection is `(cond & a) | (~cond & b)` (`impl.h:264-267`).

Nothing fails to build. There is no `#error` and no warning. The header's own text says the C path "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h`). That is an observation about specific compiler versions, not a guarantee. CI has a no-asm component (`tests/scripts/components-sanitizers.sh:105`, `component_release_test_valgrind_constant_flow_no_asm`), so the fallback is exercised under valgrind on the GCC build it targets.

There is also a gap I found by reading the guards. The 32-bit asm paths test `MBEDTLS_CT_SIZE_32` (`impl.h:142`, `:170`, `:251`). On a 32-bit ARM or x86 build with 64-bit MPIs, `mbedtls_ct_uint_t` is 64-bit and those operations fall through to C even when asm is enabled. The AArch64 path accepts both sizes. Whether that matters depends on the threat model, but it is a silent difference that the docs do not mention.

## How the property is checked

- `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` and `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` make tests mark secrets as uninitialised. Any branch or address computed from a secret then shows up as an uninitialised-value error (`tests/scripts/components-sanitizers.sh:33`, `:72`, `:105`).
- `tests/suites/test_suite_constant_time*.function` and others carry `TEST_CF_SECRET` and `TEST_CF_PUBLIC` annotations. About nine files reference them.
- The macros live in `framework/tests/include/test/constant_flow.h`, but `framework` is an empty submodule in this checkout (`.gitmodules`), so I could not read their definitions.

This checks data-dependent control flow and memory addressing. It does not check cache behavior, branch-predictor effects or timing. `SECURITY.md:50-70` says so directly: protection is "limited," and the project is "moving towards" fully timing-invariant code but "has not reached this point yet."

## How far it reaches

About 25 library files call `mbedtls_ct_` functions. Counts are from grep:

| Area | Files | Typical use |
|---|---|---|
| Bignum | `bignum_core.c` (32), `bignum.c` (26), `bignum_mod_raw.c` | Conditional copies and selects, e.g. `bignum_core.c:576` |
| RSA | `rsa.c` (37) | PKCS#1 v1.5 and OAEP unpadding checks, signature compare (`:2049`, `:2530`, `:2774`) |
| CBC padding | `cipher.c` (30) | Padding validation with no early exit (`:861-876`) |
| TLS records | `ssl_msg.c` (24) | `mbedtls_ct_hmac` and `memcpy_if` for CBC-MAC recovery (`:66`, `:147`, `:187`, `:2044-2071`) |
| TLS handshake | `ssl_tls12_client.c`, `ssl_cookie.c`, `ssl_tls13_*` | Finished and cookie compares |
| Tag checks | `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `nist_kw.c` | `mbedtls_ct_memcmp` on tags |
| PSA | `psa_crypto.c` (9), `psa_crypto_mac.c`, `psa_crypto_cipher.c` | Hash, MAC and cipher compares |
| Encoding | `base64.c` (21) | Table-free decoding |

Not covered by direct calls: `aes.c`, `ecp.c`, `ecdh.c`, `ecdsa.c`, `dhm.c` and `ecjpake.c` contain no `mbedtls_ct_` call. Their secret-handling constant-time properties depend on whatever bignum or table code they call, which I did not audit. PSA has no equivalent API; the docs tell users to keep using `constant_time.h` (`docs/psa-transition.md:284`).

## What I did not verify

- I did not compile the library or run the valgrind or MSan components.
- I did not inspect the `framework` submodule, so the exact definitions of the constant-flow macros are unverified.
- I did not audit the ECC or DH scalar-multiplication paths, which may be constant-time through bignum internals rather than direct calls.