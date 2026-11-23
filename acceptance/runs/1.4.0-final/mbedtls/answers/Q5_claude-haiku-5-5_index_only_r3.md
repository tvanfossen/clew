## Short answer

Constant-time behaviour in mbedtls is enforced by convention and a small set of primitives, not by a compiler-checked guarantee. The primitives use inline assembly where the target allows it, and fall back to plain C with an optimizer barrier elsewhere. Nothing in the index shows a build-time refusal for an unsupported compiler. Verification is dynamic (Valgrind), and the security policy explicitly disclaims guarantees against local non-timing attacks. The index does not confirm that the whole library is constant-time.

## How it is enforced at the instruction level

All of this lives in `library/constant_time_impl.h`, with helpers in `library/constant_time.c`.

- **Masks instead of branches.** A condition is `mbedtls_ct_condition_t`, an all-zeros or all-ones word. `mbedtls_ct_bool(x)` turns a value into a mask. On AArch64 it is `neg; orr; asr #63`, so the mask is produced without a branch (`constant_time_impl.h:120`). Similar sequences exist for ARMv7-M Thumb, x86-64 and x86-32.
- **Comparisons are bit arithmetic.** `mbedtls_ct_uint_lt` is a borrow-propagation sequence (`sub`, `bic`, `and`, `orr`, `asr`) rather than a `<` (`constant_time_impl.h:271`).
- **Selection is masked copy.** `mbedtls_ct_memcpy_if` computes `(src1 & mask) | (src2 & ~mask)` word by word, always reading both sources (`library/constant_time.c:169`).
- **Comparison reads everything.** `mbedtls_ct_memcmp` casts both buffers to `volatile`, so the compiler cannot exit early on the first difference. It XORs all bytes and returns a value that is non-zero iff the buffers differ (`library/constant_time.c:67`). Its documentation says it is not constant-time with respect to `n`.
- **Opaque values.** `mbedtls_ct_compiler_opaque(x)` is an empty `asm volatile` with `"+r"(x)` when assembly is enabled. Otherwise it returns `x ^ mbedtls_ct_zero`, where `mbedtls_ct_zero` is a `volatile` global (`constant_time_impl.h:85`, `constant_time.c:29`). Its purpose is to stop the compiler from knowing a condition's value, so it cannot reintroduce a branch.

The raw-assembly paths are only used when `MBEDTLS_CT_ASM` is defined. That macro requires `MBEDTLS_HAVE_ASM` and either GCC-style or ARMCC compiler detection (`constant_time_impl.h:42`, gated on lines 40–52). Size-specific variants are selected by `MBEDTLS_CT_SIZE_32` or `MBEDTLS_CT_SIZE_64`.

## What happens on a compiler that cannot support it

- **Without `MBEDTLS_CT_ASM`** (no asm support, or a compiler other than GCC/Clang or ARMCC, such as MSVC), the same helpers compile as portable C. The C fallback for `mbedtls_ct_bool` uses the sign-bit trick: `y = (-xo) | -(xo >> 1)`, then shifts and negates (`constant_time_impl.h:120`, fallback branch).
- **The guarantee weakens to a best effort.** The code comment says the C fallback "does not get optimised into conditional instructions or branches" by trunk clang, gcc or MSVC v19 as of May 2023. That is a dated observation about specific compiler versions, not a property the code enforces.
- **No refusal found.** The index shows no `#error` or configuration check that rejects a non-asm build when constant time is needed. The only `#error` in `constant_time.c` concerns `int` width in `mbedtls_ct_memcmp`.
- **Documented caveat.** `SECURITY.md` says compilers can introduce timing side channels in code meant to be constant-time, that mbedtls includes countermeasures, and that "given the diversity of compilers, compiler options…" can still matter. The index snippet is truncated, so I cannot quote the full caveat.

## How it is checked

- **Dynamic only.** `test_with_valgrind_constant_time` runs the `tests/suites/*constant_time*.data` suites under Valgrind (`tests/scripts/components-configuration-crypto.sh:25`). It excludes slow suites and the HMAC constant-time suite (via `GLOBIGNORE`), which is worth noting because that suite is one of the ones it skips.
- **Gate symbols.** `CT_VALGRIND` and `CT_MEMSAN` appear among the gate symbols in the index. I did not read what they control.
- **Documented method.** The shared-memory design doc notes that Valgrind memory poisoning is already used for constant-flow testing, and that MSan is considered as an alternative. That confirms the method, not its coverage.

## How far it reaches

The primitives have callers in these places. This is the list the index found through dossier caller lookups, not an exhaustive census.

| Area | Users of constant-time primitives |
|---|---|
| Tag and MAC verification | `mbedtls_gcm_auth_decrypt`, `mbedtls_ccm_compare_tags`, `mbedtls_chachapoly_auth_decrypt`, `mbedtls_cipher_check_tag`, `mbedtls_nist_kw_unwrap`, `psa_mac_verify_finish`, `psa_hash_verify` / `psa_hash_compare` |
| RSA | `mbedtls_rsa_rsaes_oaep_decrypt`, `mbedtls_ct_rsaes_pkcs1_v15_unpadding`, PKCS#1 v1.5 sign/verify |
| Block-cipher padding | `get_one_and_zeros_padding`, `get_zeros_and_len_padding` (`cipher.c`), `psa_cipher_finish` |
| Bignum | `mbedtls_mpi_core_lt_ct`, `mbedtls_mpi_core_montmul`, `mbedtls_mpi_core_check_zero_ct`, `mbedtls_mpi_core_gcd_modinv_odd`, `mbedtls_mpi_safe_cond_assign/swap`, `mbedtls_mpi_mod_raw_cond_assign/swap` |
| TLS | `ssl_parse_encrypted_pms` (TLS 1.2 premaster secret), `mbedtls_ct_hmac` (record MAC in `ssl_msg.c`), `ssl_parse_client_psk_identity`, TLS 1.3 binder and identity checks, `ssl_tls_parse_finished` and `ssl_tls13_parse_finished_message` |
| Cookies and DTLS | `mbedtls_ssl_cookie_check` |

Separately, `3rdparty/p256-m` is described as fully constant-time "from the ground up". It computes modular inversion with Fermat's little theorem, and it has a `MUL64_IS_CONSTANT_TIME` option for platforms with a constant-time 32×32→64 multiply. `3rdparty/everest` supplies X25519 and related code. These are vendored implementations with their own design, not part of the `constant_time` facility.

## What the index cannot settle

- Whether every secret-dependent path in the library (for example scalar multiplication in `ecp.c`, or AES table lookups) uses these helpers. I did not find evidence either way in the index.
- Whether the C fallback is exercised under Valgrind in CI, as opposed to the assembly paths.
- The full text of the `SECURITY.md` caveat.

To close these, read `library/ecp.c` and the CI configuration directly, or run the Valgrind suite on a non-asm build.