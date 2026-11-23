The short answer: constant-time behaviour is a convention the library builds by hand, not something the compiler is required to preserve. Hand-written assembly covers a few primitives on four architectures, and a C fallback covers everything else. Nothing at build time checks that the output is actually constant-time. The protection is partial, and the library says so in `SECURITY.md`.

**How it is enforced at the instruction level**

The facility is `library/constant_time_impl.h`, with declarations in `library/constant_time_internal.h` and one public function, `mbedtls_ct_memcmp`, in `include/mbedtls/constant_time.h`. The design has three parts:

- **No comparison operators on secrets.** `mbedtls_ct_bool(x)` turns any value into an all-ones or all-zeros mask using `neg`/`or`/`sar` (or the C equivalent, `(-x | -(x>>1))`, then take the sign bit). Comparisons like `mbedtls_ct_uint_lt` are built from subtraction and masks, and selection is `(cond & a) | (~cond & b)`. The code never branches on a secret.
- **Opacity barrier.** `mbedtls_ct_compiler_opaque(x)` is `asm volatile("" : "+r"(x))` where assembly is available. Otherwise it is `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` zero, so the optimiser cannot prove the value. This stops the compiler from folding a secret into a branch when it happens to know the value.
- **Full-length, volatile memory access.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers, always runs to `n`, and ORs the XOR differences together. It has no early exit. `mbedtls_ct_memcpy_if` always reads both sources and blends with masks. `mbedtls_ct_memcpy_offset` loops over every candidate offset, so the access pattern depends on `offset_min`/`offset_max`, not on the secret offset.

The hand-written assembly exists only for the primitives: `mbedtls_ct_bool`, `mbedtls_ct_if`, `mbedtls_ct_uint_lt`, and the opaque barrier. It is provided for 32-bit ARM/Thumb, AArch64, x86, and x86-64. `mbedtls_ct_memcmp` itself is plain C, even on x86.

**What happens on a compiler or target that cannot support it**

The selection is a preprocessor decision in `constant_time_impl.h`:

```
MBEDTLS_CT_ASM  <=  MBEDTLS_HAVE_ASM && __GNUC__ && (not armcc5)
   + one of: ARM / AArch64 / x86-64 / x86 (by __arm__, __aarch64__, __x86_64__, __i386__)
```

Anything else takes the C fallback silently:

| Situation | Result |
|---|---|
| MSVC, IAR, other non-GNU compilers | C fallback, no warning |
| armcc5 | C fallback |
| `MBEDTLS_HAVE_ASM` disabled in config | C fallback |
| Other architectures (RISC-V, MIPS, Xtensa, …) | C fallback |
| MemSan build | `check_config.h` makes `MBEDTLS_HAS_MEMSAN` plus `MBEDTLS_HAVE_ASM` a hard `#error`, so sanitizer builds are forced onto C |

The only `#error`s in the module guard the unaligned-volatile helper and the requirement for at least 32-bit `int`. Neither concerns the constant-time property. The C fallback's comment says it has been "observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an empirical observation about specific compiler versions, not a guarantee, and the same comment says it is "fairly inefficient".

**How far it reaches**

- **Public API:** only `mbedtls_ct_memcmp`.
- **Internal users (grep counts of `mbedtls_ct_`):** `rsa.c` (about 37 sites, including PKCS#1 v1.5 unpadding and signature comparison), `cipher.c` (about 30, CBC padding removal), `ssl_msg.c` (about 33, record MAC and padding check, `mbedtls_ct_hmac`), `bignum_core.c` (about 39), `base64.c` (about 21), `psa_crypto*.c`, `ssl_tls12_server.c`, `nist_kw.c`, and `ccm.c`, `gcm.c`, `chachapoly.c` for tag comparison.
- **Elliptic curves:** `ecp.c` does not call `mbedtls_ct_*` directly. It uses `mbedtls_mpi_safe_cond_assign`/`swap` in the bignum layer, which is a separate mechanism.
- **Not everywhere:** I did not audit every secret-dependent comparison in the library. Many plain `memcmp` or branch sites outside these modules were not checked. `3rdparty/p256-m` has its own constant-flow design and does not use this module.
- **Testing:** `tests/suites/test_suite_constant_time.function` is instrumented with `TEST_CF_SECRET`/`TEST_CF_PUBLIC`, which come from the `framework` submodule. In this checkout `framework/` is an empty gitlink, so that suite cannot build here, and I did not build or run anything. The intended checks are Valgrind memcheck (`components-configuration-crypto.sh`, with `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`) and MemSan (`components-sanitizers.sh`, C path only). Both are taint-style checks for secret-dependent branches and addresses on the tested paths. They do not measure hardware timing, such as cache or branch-predictor effects. `SECURITY.md` says the protection is "limited" and aims only at "publicly documented attack techniques".