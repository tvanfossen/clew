## Short answer

Constant-time behaviour in mbedtls is a convention enforced by construction, not a guarantee the toolchain checks. Secret-dependent values are handled as all-ones or all-zero bitmasks, combined with bitwise operations. Inline asm on four architectures stops the optimizer from turning those masks back into branches. Everywhere else, a plain C fallback is used, and nothing verifies that it stayed branch-free. The facility is used in the places that handle secrets, but not across the whole library. I read the source and did not compile or disassemble anything, so the instruction-level claims are from the code, not from generated output.

## How it is enforced at the instruction level

The primitives live in `library/constant_time_impl.h` and are declared in `library/constant_time_internal.h`. The header says `mbedtls_ct_condition_t` must be treated as opaque. `mbedtls_ct_bool(x)` turns any non-zero value into an all-ones mask, and `mbedtls_ct_if`, `mbedtls_ct_uint_lt` and the rest are built from `&`, `|`, `^` and arithmetic on that mask.

Two mechanisms stop the compiler from undoing this:

- **`mbedtls_ct_compiler_opaque(x)`** (`constant_time_impl.h:85`). With asm, it is an empty `asm volatile("" : [x] "+r"(x))`, so the compiler cannot prove the value. Without asm, it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` zero defined in `library/constant_time.c:29`.
- **Hand-written asm per ISA.** `constant_time_impl.h` defines `MBEDTLS_CT_ASM` only when `MBEDTLS_HAVE_ASM` is set, the compiler is GNU-compatible (`__GNUC__`, and not old armcc5), and the target is one of: 32-bit ARM/Thumb (`MBEDTLS_CT_ARM_ASM`), AArch64, x86-64, or i386. Each primitive has a branch-free sequence for each of these. For example, x86-64 `mbedtls_ct_bool` is `mov; neg; or; sar $63`, and `mbedtls_ct_uint_lt` is a sign-of-difference computation with no `cmp`/`jcc`.

## What happens on a compiler that cannot support it

The `#else` branches are plain C. Each primitive is written with masks and avoids comparison operators, plus the volatile-zero barrier. The header's own comment says this is "observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an observation about compiler output at one point in time, not a guarantee.

The fallback triggers when any of these holds:

- `MBEDTLS_HAVE_ASM` is undefined. It is on by default in `include/mbedtls/mbedtls_config.h:52`.
- The compiler is not GNU-compatible, such as MSVC or IAR.
- The target is not one of the four covered ISAs.

There is no `#error` and no warning. The build succeeds and the constant-time guarantee quietly weakens to "whatever the compiler does with C". `mbedtls_ct_memcmp` also depends on `volatile` to force full reads, and that too is a C-level request.

## How far it reaches

The `mbedtls_ct_*` / `MBEDTLS_CT_*` symbols and the `constant_time` header appear in about 35 library files, roughly 444 occurrences in total.

| Area | Where the facility is used |
|---|---|
| RSA | PKCS#1 v1.5 decrypt and verify, OAEP decrypt (`rsa.c`), using `mbedtls_ct_zeroize_if` and "bad" flags |
| Bignum | `bignum_core.c`, `bignum_mod_raw.c`, `bignum.c`: `mbedtls_mpi_core_lt_ct`, `check_zero_ct`, the odd-modulus GCD/inverse path |
| ECC | `ecp.c` builds on `mbedtls_mpi_safe_cond_assign` / `swap`. `ecp_select_comb` reads the whole precomputed table, and the comb recoding uses constant-time parity fixing |
| AEAD and MAC tag checks | `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c`, `cipher.c` (`mbedtls_cipher_check_tag`), `nist_kw.c`, and PSA MAC/hash verify |
| TLS | `ssl_msg.c` record decryption and padding, `ssl_tls12_server.c` and `ssl_tls13_server.c` (PSK binder and identity), Finished verification, `ssl_cookie.c` |
| Other | `base64.c`, the PSA driver wrappers |

Things that are explicitly not constant-time, per their comments:

- `mbedtls_ecp_mul_shortcuts` (`ecp.c` ~2734) is marked "NOT constant-time". It takes shortcuts for m = 0, 1 and -1.
- `mbedtls_ecp_muladd_restartable` (`ecp.c` ~2769) is marked "NOT constant-time".
- The `mbedtls_ct_memcmp` documentation says it is not constant-time with respect to `n`, which is treated as public.

The grep found no constant-time primitive in `aes.c`, `dhm.c`, `ecdsa.c`, or the hash files. Software AES table lookups therefore appear to be outside this facility, with the usual cache-timing caveat. I did not verify AES table design, so treat that as a likely gap, not a confirmed one.

## How it is checked

- `tests/scripts/components-configuration-crypto.sh` runs the `*constant_time*` suites under Valgrind memcheck, with `--track-origins=yes`. Memcheck flags branches on undefined data, which is how secret-dependence is detected.
- `test_suite_constant_time.function` says it relies on `framework/tests/include/test/constant_flow.h`, which is not present in this checkout because the framework submodule is absent. I could not confirm how secrets are marked.
- Valgrind runs only the dedicated constant-time suites, and `test_suite_constant_time_hmac.data` is excluded. Other modules that use the primitives are covered only indirectly.

## Limits to keep in mind

- Constant-time is per-operation. Variable-latency instructions in other code, and length-dependent loops such as `mbedtls_ct_memcmp`'s over `n`, are outside the guarantee.
- The asm path is only as good as its instruction selection. `asm volatile` keeps the block in place, but it does not prove the surrounding C stays branch-free.