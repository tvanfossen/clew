**Short answer:** Constant-time is enforced by coding discipline, not by the compiler. mbedtls writes secret-dependent logic as branch-free mask arithmetic, uses a barrier to stop the optimizer from seeing through it, and uses hand-written assembly on a few targets. Then it checks the result at test time with Valgrind. Nothing in the build fails if the code is compiled into a branch. On a compiler without the assembly path, it falls back to plain C with no hard guarantee. The helpers are used in the padding, MAC, tag and bignum code paths, and SECURITY.md disclaims the rest.

**How it works at the instruction level**

- **Masks instead of branches.** `library/constant_time_impl.h` builds a `mbedtls_ct_condition_t` that is all-ones or all-zeros. `mbedtls_ct_bool` (line 120) turns a value into a mask: nonzero becomes `-1`, zero becomes `0`. Selection and comparison helpers (`mbedtls_ct_uint_if`, `mbedtls_ct_uint_eq`, `mbedtls_ct_bool_and`, etc.) are built on that mask, so secret values never reach a conditional jump.
- **Assembly on four targets.** `mbedtls_ct_bool` has inline asm for AArch64, 32-bit ARM, x86_64 and 32-bit x86. The x86_64 version is `mov; neg; or; sar $63`, which produces the mask with no branch. The assembly is only used when the type width matches (`MBEDTLS_CT_SIZE` is 32 or 64 bits).
- **Optimizer barrier.** `mbedtls_ct_compiler_opaque` (line 85) hides the value from the compiler. With assembly it is `asm volatile("" : "+r"(x))`. Without it, it XORs with `mbedtls_ct_zero`, a `volatile` global, so the compiler cannot prove the value is constant. The header's comments say the plain-C fallback "does not get optimised into conditional instructions or branches" by recent clang, GCC or MSVC, but that is a claim about the versions tested, not a guarantee.
- **Volatile reads in memcmp.** `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers and ORs the XOR differences. It does not exit early, so a branch cannot end the loop sooner on a mismatch. Its doc says it is not constant with respect to `n`, the length.

**What happens on a compiler that cannot support it**

- The assembly is gated by `MBEDTLS_CT_ASM`, which is defined only under `MBEDTLS_HAVE_ASM` and only when the compiler is GCC-compatible or ARMCC (`constant_time_impl.h:40-52`). `constant_time.c:23` also checks `#if !defined(MBEDTLS_CT_ASM)`.
- On any other compiler, such as MSVC, or with `MBEDTLS_HAVE_ASM` off, the build does not fail. It silently uses the plain-C mask code and the volatile-zero opaque barrier.
- The library does not warn about the downgrade. Whether the compiler keeps the masks branch-free is then up to that compiler.

**How it is verified**

- `tests/scripts/components-configuration-crypto.sh:25` runs the `*constant_time*.data` suites under Valgrind.
- `tests/scripts/components-sanitizers.sh:72` is a release build with `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND`. Secrets are marked uninitialized, so Valgrind reports any branch or memory index that depends on them. It also runs the `test_suite_constant_time` suite again with the assembly path enabled, since the default run covers only the plain-C path.
- `scripts/config.py` has an `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` option that needs clang with MemorySanitizer, as a second checker.
- These are runtime checks on the binaries the tests build. They do not check every compiler or optimization level.

**How far it reaches**

The helpers are used in the places where a secret-dependent branch would leak a padding or MAC result:

| Area | Where it is used |
|---|---|
| RSA decryption | PKCS#1 v1.5 unpadding (`library/rsa.c:420`), OAEP decrypt (`rsa.c:1974`) |
| Block cipher padding | `library/cipher.c`: `get_zeros_padding`, `get_one_and_zeros_padding`, `get_zeros_and_len_padding`, `mbedtls_get_pkcs_padding` |
| TLS record MAC | `mbedtls_ct_hmac` (`library/ssl_msg.c:65`), which hashes every possible length and keeps the right result |
| Tag and hash comparison | `mbedtls_ct_memcmp` is called from CCM, GCM, ChaCha20-Poly1305, NIST KW, PSA MAC/hash verify, and TLS Finished and PSK-binder checks |
| Bignum core | `mbedtls_mpi_core_lt_ct`, `check_zero_ct`, `montmul`, `gcd_modinv_odd`, conditional assign and swap, table lookup |
| Base64 | `mbedtls_ct_base64_enc_char` and `dec_value` |

Outside the library, the third-party `everest` (X25519) and `p256-m` code claim constant-time behaviour in their own comments and READMEs. `MUL64_IS_CONSTANT_TIME` is a config symbol in p256-m that depends on the target having a constant-time 32×32→64 multiply.

**What is not covered**

- SECURITY.md says the pure-software implementation uses lookup tables, which are vulnerable to timing attacks. It also says compilers can introduce timing side channels into code meant to be constant-time, and that there are no guarantees against local non-timing side channels.
- `mbedtls_ct_memcmp` is not constant with respect to length.
- `mbedtls_mpi_core_check_zero_ct` is constant with respect to the value, not the number of limbs.
- PSA's AEAD verify asks implementations to make "best effort" on tag comparison.

**Limits of this answer:** I read the index's summaries and the bodies it returned. I did not read the body of the `constant_time.c:23` fallback block, or the bodies of `mbedtls_ct_uint_lt` and the x86 32-bit `mbedtls_ct_if` path, and I did not check the individual call sites in cipher.c or ssl_msg.c beyond what the index returned.