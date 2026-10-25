## Short answer

Constant-time behaviour is not enforced by the compiler or by any build-time check. It rests on two things. First, hand-written inline assembly for the mask primitives on a few architectures. Second, a volatile-based C fallback that is only believed to survive the optimizer. Nothing fails the build if the fallback is used. The facility is opt-in per call site, and it does not cover everything secret-dependent in the library.

## How it works at the instruction level

All branch-free logic is built from one primitive, `mbedtls_ct_condition_t`: an all-ones mask (true) or all-zeros mask (false). `constant_time_internal.h:45-47` says the type is opaque and the compiler should never be able to prove its value.

Every other operation is built on it:

- **Comparisons** (`mbedtls_ct_uint_lt`, `_eq`, `_ge`…) produce a mask.
- **Selection** (`mbedtls_ct_if`, `_if_else_0`) is `(cond & a) | (~cond & b)`.
- **Block operations** (`mbedtls_ct_memcmp`, `mbedtls_ct_memcpy_if`, `mbedtls_ct_memcpy_offset`, `mbedtls_ct_zeroize_if`, `mbedtls_ct_memmove_left`) touch every byte, with a volatile read on each access so the compiler cannot exit early. `memcmp` ORs the XOR of all bytes (`constant_time.c:67-116`). `memcpy_offset` loops over every candidate offset from `offset_min` to `offset_max` (`constant_time.c:214-227`).

The optimizer is kept away from the values in one of two ways:

| Path | Mechanism | Where |
|---|---|---|
| Inline asm (GNU compilers, supported arch) | `asm volatile` sequences for `bool`, `if`, `uint_lt`, plus `compiler_opaque` as an empty asm that pins `x` in a register | `constant_time_impl.h:85-93`, `120-349` |
| C fallback | `compiler_opaque(x) = x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a global `volatile` zero; comparisons use `(x-y)` sign-bit arithmetic | `constant_time.c:23-30`, `impl.h:265-267`, `350-378` |

Example, the x86-64 `mbedtls_ct_bool` (`impl.h:157-169`): `s = x; s = -s; x |= s; s >>= 63` gives all-ones iff `x != 0`, with no flags-dependent branch.

The asm variants are gated by `MBEDTLS_CT_SIZE_32`/`_64`, so a given arch may get asm for some operand widths and C for others.

## What happens on a compiler that cannot support it

The asm path is chosen in `constant_time_impl.h:40-52`:

- Requires `MBEDTLS_HAVE_ASM` (`mbedtls_config.h:52`), `__GNUC__`, and not armcc5.
- Arch detection: ARM/Thumb, AArch64, x86-64, or i386. Anything else gets no `MBEDTLS_CT_*_ASM` macro.

So MSVC, IAR, armcc5, other GNU-compatible targets such as RISC-V or MIPS, and any build with `MBEDTLS_HAVE_ASM` undefined silently take the C path. There is no `#error`, warning, or runtime indication. The fallback is still functionally correct. What it loses is the timing guarantee.

The header states the status plainly: the C fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023" (`constant_time_internal.h:55-59`). That is an observation about specific compiler versions, not a contract. The public header is also hedged: the functions are "likely to be compiled" branch-free, and `mbedtls_ct_memcmp` is explicitly "not constant-time w.r.t. `n`" (`include/mbedtls/constant_time.h:14-20`).

Two build-time interactions are worth knowing:
- `check_config.h:250` makes `MBEDTLS_HAS_MEMSAN` plus `MBEDTLS_HAVE_ASM` a hard error, so MemorySanitizer builds run the C path.
- `check_config.h:1063` makes a forced `MBEDTLS_HAVE_INT32/64` plus `MBEDTLS_HAVE_ASM` a hard error.

## How far it reaches

Call-site counts (pattern `mbedtls_ct_\w+\(` under `library/`): 286 occurrences in 29 files. About 100 of those are definitions and declarations inside the three `constant_time*` headers and `.c`, so the consumer count is roughly 180.

| Area | Files | Use |
|---|---|---|
| RSA PKCS#1 v1.5 | `rsa.c` (29) | `mbedtls_ct_rsaes_pkcs1_v15_unpadding`, padding checks and error selection |
| Symmetric padding | `cipher.c` (25) | CBC padding removal |
| TLS record layer | `ssl_msg.c` (22) | `mbedtls_ct_hmac` (`ssl_msg.c:66`, `:187`), MAC compare (`:1798`, `:2071`), CBC pad check |
| Bignum | `bignum.c` (21), `bignum_core.c` (22), `bignum_mod_raw.c` (2) | `_ct` compare and select helpers |
| Base64 | `base64.c` (21) | Decoding without data-dependent branches |
| Key wrap | `nist_kw.c` (4) | `mbedtls_ct_memcmp_partial` |
| TLS server/client | `ssl_tls12_server.c` (7), others | Assorted |
| PSA | `psa_crypto.c` (7), `psa_crypto_cipher.c` (3), `psa_crypto_mac.c` (1) | Tag and key handling |
| AEAD/MAC | `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c` (1 each) | Tag compare; I did not read these call sites |

Things the facility does **not** cover, based on this search:

- `ecp.c`, `ecp_curves.c` and `aes.c` have no `mbedtls_ct_*` calls. The text "constant time" appears in their comments, but the helpers are not used. I did not verify how ECC scalar multiplication or AES table lookups achieve their timing properties. Those are the first places to look if you need a timing audit.
- `3rdparty/p256-m` and `3rdparty/everest` have their own constant-time code (`MUL64_IS_CONSTANT_TIME`, the kremlib carry functions). They do not use this module.
- Any secret-dependent `if` in code that never adopted the helpers is invisible to this facility. Nothing enforces adoption.

## How it is tested

- Unit tests in `tests/suites/test_suite_constant_time*.function` and related suites. They mark secrets with `TEST_CF_SECRET`/`TEST_CF_PUBLIC`. I could not find those macros defined anywhere in this checkout, so they probably come from an external test framework.
- Valgrind mode (`MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`, `mbedtls_config.h:2126-2142`), run through `test_with_valgrind_constant_time` in `tests/scripts/components-configuration-crypto.sh`. Memcheck reports branches or addresses that depend on uninitialised (secret) data.
- MemorySanitizer mode (`MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN`, `mbedtls_config.h:2109-2123`), wired up in `tests/scripts/components-sanitizers.sh`. It requires clang and the C path, since asm is disallowed under MSan.

These checks are dynamic. They only see the paths the tests exercise, and they only detect leaks on the compiler and platform where they run. Passing them does not prove the asm-free fallback is constant-time on other toolchains.

## Bottom line

On GCC/Clang for ARM, AArch64, and x86, the mask primitives are asm and the optimizer cannot undo them. Everywhere else the protection is a volatile-based C idiom that works in practice on the compilers the authors tested. Adoption is manual and incomplete: RSA unpadding, CBC/MAC checks, base64, and bignum helpers use it, while ECC scalar multiplication and AES do not show up in this search.