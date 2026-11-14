**Short answer:** nothing enforces constant time at build time. The library relies on hand-written assembly for a few mask primitives where the target allows it, a portable C fallback everywhere else, and a Valgrind "constant flow" test in CI as the only check that catches regressions. The index cannot show the generated machine code, so the instruction-level claims below come from reading the source bodies, not from a disassembly.

**How it works at the instruction level**

All the primitives live in `library/constant_time_impl.h`. The core pattern is a branch-free mask. `mbedtls_ct_bool(x)` returns all-ones if `x != 0` and zero otherwise.

- **Assembly path** (`library/constant_time_impl.h:120`): on AArch64, 32-bit ARM (Thumb-aware), x86-64 and x86-32, `mbedtls_ct_bool` uses inline `asm volatile` (`neg`/`orr`/`asr` on AArch64, `neg`/`or`/`sar` on x86). `mbedtls_ct_uint_lt` (`:271`) and `mbedtls_ct_if` (`:205`) have the same per-architecture asm variants.
- **C fallback** (`:120–203`): computes the sign bit of `(-x) | -(x>>1)` and negates it into a mask. The header's own comment says this was checked as of May 2023 to not be turned into branches or conditional moves by trunk clang, gcc or MSVC 19. That is a statement about specific compiler versions, not a guarantee.
- **Optimizer barrier**: `mbedtls_ct_compiler_opaque` (`:85`) is an empty `asm volatile` that forces the value through a register. Without asm it XORs with `mbedtls_ct_zero`, a `volatile` global that is 0 (`constant_time.c:29`), so the compiler cannot fold the value at compile time.
- **Byte comparison**: `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers and ORs the XOR differences, so it cannot exit early. It is documented as constant-time with respect to the data but not with respect to `n`.

**What happens on a compiler or target without the asm**

`MBEDTLS_CT_ASM` (`constant_time_impl.h:42`) is defined only when `MBEDTLS_HAVE_ASM` is on and the compiler is GCC-compatible or ARMCC (`__GNUC__` / `__ARMCC_VERSION`, lines 40–52). Otherwise the C fallback is used, with no build error, warning or runtime check. The only compile-time refusal in this area is an `#error` in `mbedtls_ct_memcmp` for `int` narrower than 32 bits, which is about integer width, not compiler capability. So on an unsupported toolchain the library quietly relies on the C fallback surviving that compiler's optimizer, and nothing in the build says so.

**How it is checked**

- `tests/scripts/components-configuration-crypto.sh` (`test_with_valgrind_constant_time`) runs the `tests/suites/*constant_time*.data` suites under Valgrind.
- `tests/scripts/components-sanitizers.sh` (`component_release_test_valgrind_constant_flow`) runs the same constant-time tests under Valgrind in a release build.
- `docs/architecture/psa-shared-memory.md` says Valgrind memory poisoning is the constant-flow testing method.

These tests run only on the platforms CI covers, so they do not prove anything about other compilers or targets.

**How far it reaches**

The index shows the header included by roughly 20 library files and called from many more:

| Area | Files / functions (from the index) |
|---|---|
| Bignum | `bignum_core.c`, `bignum.c`, `bignum_mod.c`, `bignum_mod_raw.c` (CT comparisons, conditional assign/swap, zero check, GCD/modinv) |
| ECC | `ecp_curves.c` includes it; the index does not show it reaching scalar multiplication in `ecp.c` |
| RSA | `rsa.c`: PKCS#1 v1.5 unpadding, OAEP decrypt, v1.5 sign/verify |
| Cipher modes | `cipher.c` (padding removal, tag check), `gcm.c`, `ccm.c`, `chachapoly.c`, `nist_kw.c`, `cmac.c` |
| TLS | `ssl_msg.c` decrypt, `ssl_tls.c` Finished check, TLS 1.2 server PSK identity and pre-master decrypt, TLS 1.3 binder/Finished checks, cookie check |
| PSA | `psa_crypto.c` hash/MAC/AEAD verify, `psa_crypto_cipher.c`, `psa_crypto_mac.c` |

Two limits on that list:

- Search results were capped at 25 rows, so the caller list may be incomplete.
- `p256-m` under `3rdparty/` is a separate constant-time design with its own README. It has its own config symbol `MUL64_IS_CONSTANT_TIME` and does not use the Mbed TLS helpers.

**Scope disclaimers**

`SECURITY.md` says compilers can introduce timing side channels into code intended to be constant-time, and that exploitable ones are treated as vulnerabilities. It also says Mbed TLS makes no guarantee against local non-timing side channels. The PSA docs note that the PSA API has no equivalent of these utilities, and that the PSA AEAD verify spec asks only for a "best effort" constant-time tag comparison.