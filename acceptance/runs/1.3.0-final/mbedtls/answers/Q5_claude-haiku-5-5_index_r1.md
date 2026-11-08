## Short answer

Constant-time behaviour is not enforced by the build. It is a convention: branch-free C, plus a small set of hand-written assembly barriers on a few architectures, with compiler-behaviour assumptions behind them. Nothing fails the build if a compiler breaks it, and the library's own documentation says the protection is limited. Reach is wide, but mostly for the code the designers judged timing-sensitive.

## How it works at the instruction level

The primitives live in `library/constant_time_impl.h`, with declarations in `constant_time_internal.h` and the public API in `include/mbedtls/constant_time.h`. Three ideas do the work:

1. **Masks, not branches.** `mbedtls_ct_bool(x)` turns any non-zero value into an all-ones mask (`0` or `~0`). `mbedtls_ct_if(cond, a, b)` selects with `and`/`not`/`and`/`or`. Comparisons such as `mbedtls_ct_uint_lt` are built from the sign bit of a subtraction. Callers then combine masks with `mbedtls_ct_bool_and/or/not`.

2. **An opacity barrier.** `mbedtls_ct_compiler_opaque(x)` stops the optimiser from learning the value of a secret:
   - With assembly (`MBEDTLS_CT_ASM`), it is `asm volatile("" : [x] "+r"(x))`. The empty asm claims to read and write the register, so the compiler cannot fold or prove anything about it.
   - Without assembly, it returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global set to 0. The compiler has to assume it could be changed, so it cannot prove the XOR is a no-op.

3. **Hand-written asm for the core primitives.** When `MBEDTLS_CT_ASM` is defined, `mbedtls_ct_bool` and `mbedtls_ct_if` each have per-architecture asm variants: ARM (Thumb/ARM32), AArch64, x86-64 and x86-32. They cover 32-bit and 64-bit `mbedtls_ct_uint_t`, selected by `MBEDTLS_CT_SIZE_32`/`_64`.

`mbedtls_ct_memcmp` (`library/constant_time.c:67`) is the clearest example of the approach. It reads both buffers through `volatile` pointers, ORs the XOR of every byte into `diff` with no early exit, and returns a value that is zero only when `diff` is zero. It is constant with respect to the data but not to `n`, which its doc states.

## What happens on a compiler that cannot support it

Asm is enabled only when `MBEDTLS_HAVE_ASM` is set, the compiler is GCC-compatible (`__GNUC__`), and it is not ARMCC older than 6. Anything else takes the C fallback.

- **No `#error`, no warning.** Selection is silent. Compilers that define `__GNUC__` but are not supported by the asm, and targets outside ARM/AArch64/x86, simply get the C path.
- **The C path is weaker by construction.** The fallback still avoids branches in the source, and the `volatile` zero is a plausible barrier. But the header only says it "does not get optimised into conditional instructions or branches by trunk clang, gcc, or MSVC v19" as of May 2023. That is a claim about specific compiler versions, not a guarantee.
- **Two hard errors only.** `check_config.h:250` rejects MemorySanitizer combined with `MBEDTLS_HAVE_ASM`, because MSan cannot handle the asm. `constant_time.c:105` rejects 16-bit `int`s in `memcmp`.
- **The library's own position.** `SECURITY.md:107-111` says compilers can introduce timing side channels, that the countermeasures "may not be complete," and that the project treats exploitable leaks as bugs only at common optimisation levels (`-O2`/`-Os`). `-O3`/`-Oz` are "less scrutinized." It also says the project is "moving towards" fully timing-invariant code "but has not reached this point yet" (`SECURITY.md:63-65`).

## How it is tested

- **Functional tests:** `tests/suites/test_suite_constant_time.*` and `test_suite_constant_time_hmac.*`.
- **Valgrind memcheck:** `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`. Secret data is marked undefined, so any branch or address computed from it is reported. Driven from `tests/scripts/components-configuration-crypto.sh:25-32` and `components-sanitizers.sh:72`.
- **MemorySanitizer:** `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN`, which requires a clang MSan build with asm disabled (`components-sanitizers.sh:33`).

One gap in my verification: I found the valgrind and MSan poisoning calls only in the third-party `3rdparty/p256-m` (`p256-m.c:36-45`), not in the library's own test harness. The `CONSTANT_FLOW` names appear in `tests/` only in config data and CI scripts. The harness is either outside this checkout or under other names. I did not confirm which library functions it actually poisons.

## How far it reaches

The `mbedtls_ct_*` identifiers appear in 27 library files, about 240 occurrences in total. That count includes the definitions. Main consumers, by occurrence count:

| Area | Files | Use |
|---|---|---|
| RSA | `rsa.c` (37) | PKCS#1 v1.5 and OAEP unpadding and comparisons |
| Bignum | `bignum_core.c` (32), `bignum.c` (26), `bignum_mod_raw.c` | constant-time compare, zero test, conditional select |
| Block-cipher padding | `cipher.c` (30) | PKCS#7 / one-and-zeros padding removal without leaking the pad length |
| TLS record layer | `ssl_msg.c` (24) | CBC padding check, `mbedtls_ct_hmac` (MAC over a secret-length record), `memcmp` of MAC |
| Base64 | `base64.c` (10) | table-free encode/decode |
| TLS handshake | `ssl_tls12_server.c`, `ssl_tls13_server.c`, `ssl_tls13_generic.c` | PSK binder and identity checks, Finished comparison |
| PSA | `psa_crypto.c`, `psa_crypto_mac.c`, `psa_crypto_cipher.c` | hash and MAC verify, `psa_crypto_driver_wrappers.h` |
| Other | `nist_kw.c`, `ssl_cookie.c`, `x509*.c` | unwrap and cookie comparisons |

AEAD tag checks (GCM, CCM, ChaCha20-Poly1305) go through `mbedtls_ct_memcmp`. The PSA verify APIs say "best effort" in `include/psa/crypto.h`.

Outside that, the reach is narrower than the question might suggest:

- **Block ciphers.** `SECURITY.md` says block ciphers "do not yet achieve full protection" against precise timing measurement. I did not check AES table-lookup code.
- **ECC.** `3rdparty/p256-m` is described as "fully constant-time from the ground up" (`p256-m/README.md`) and is a separate library with its own `MUL64_IS_CONSTANT_TIME` knob. It is not the general `mbedtls_ct_*` layer.
- **Lengths.** `mbedtls_ct_memcmp` and the record-length paths leak sizes by design.

## Bottom line

Enforcement is a combination of source discipline, compiler assumptions and asm barriers on three architectures, verified by valgrind/MSan CI on selected suites. The fallback is silent and weaker. Coverage is concentrated in RSA, bignum, padding, MAC/tag checks and handshake verification, and the project says so itself.