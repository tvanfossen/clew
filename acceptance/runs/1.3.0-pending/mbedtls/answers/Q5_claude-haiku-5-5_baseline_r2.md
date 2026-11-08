**Short answer:** mbedtls does not prove constant time at the instruction level. It makes the compiler's job harder and pins the critical instructions in assembly on four architectures. Everywhere else it relies on a C fallback that the header itself describes as "observed" to work. Timing verification is opt-in, and the reach is per-function, not library-wide. (Repo at `068ff08`.)

**How it's enforced**

- **Masks, not branches.** `mbedtls_ct_condition_t` is an all-ones or all-zeros word (`include/mbedtls/`, `library/constant_time_internal.h`). Secret conditions are built with `mbedtls_ct_bool`, which uses negate/or/shift, and selected with `mbedtls_ct_if`, which uses and/not/or. Block operations like `mbedtls_ct_memcpy_if` and `mbedtls_ct_zeroize_if` touch every byte regardless of the condition.
- **Opacity barrier.** `mbedtls_ct_compiler_opaque()` (`constant_time_impl.h`) launders a value through an empty `asm volatile` or an XOR with a volatile zero, so the compiler cannot constant-fold or prove the condition.
- **Hand-written asm.** `constant_time_impl.h` pins the instruction sequences for `mbedtls_ct_bool` and `mbedtls_ct_if` on 32-bit Arm/Thumb, AArch64, x86 and x86-64. Those are the only places where instruction selection is fixed.
- **`mbedtls_ct_memcmp`** (`library/constant_time.c:67-116`) reads both buffers through `volatile` pointers so it cannot exit early, ORs the XOR differences together, and folds the result to an int without losing bits.

**What happens on an unsupported compiler**

Selection is purely preprocessor-driven. `MBEDTLS_CT_ASM` is defined only when `MBEDTLS_HAVE_ASM` is set and `__GNUC__` is present (armcc5 is excluded). Otherwise the code uses the C fallback: `mbedtls_ct_zero` as a volatile zero, with no asm barrier and no arch-specific mask code. There is no `#error` and no warning. MSVC, or any GCC/Clang build with `MBEDTLS_HAVE_ASM` off, silently gets the C path.

Two details I read from the preprocessor logic rather than tested:

- The MemorySanitizer test mode refuses to build with asm (`check_config.h:250`), so the instrumented build is always the C path.
- A GNU-compatible compiler on an arch not listed above (e.g. RISC-V) gets the generic asm barrier but no arch-specific mask code.

The header's own comment says the C fallback "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023." That is an empirical observation, not a guarantee.

**How it's checked**

- No static tool (ct-verif, dudect or ctgrind) is wired into the repo.
- Dynamic checks are opt-in and off by default: `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` (clang MSan) and `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` (memcheck). They are commented out in `mbedtls_config.h:2123` and `:2142`, and CI enables them in `tests/scripts/components-sanitizers.sh`.
- `tests/suites/test_suite_constant_time.function` checks functional correctness. Its constant-flow instrumentation comes from `TEST_CF_SECRET`/`TEST_CF_PUBLIC`, defined in `framework/tests/include/test/constant_flow.h`. That `framework/` submodule is empty in this checkout, so I could not inspect those macros or confirm the suite builds here.

**How far it reaches**

Roughly 79 files reference the facility. Primitive-use counts in `library/`:

| Module | Uses | Role |
|---|---|---|
| `rsa.c` | 37 | PKCS#1 v1.5 unpadding, `mbedtls_ct_zeroize_if` on failure |
| `bignum_core.c` / `bignum.c` | 32 / 26 | Limb operations; some documented as CT with respect to parameters |
| `cipher.c` | 30 | CBC padding removal |
| `ssl_msg.c` | 24 | TLS record MAC and padding checks, `mbedtls_ct_hmac`, `mbedtls_ct_memcmp` |
| `base64.c` | 21 | Table-free encoding |
| `ecp.c` | 15 | Comb recoding and parity fix; several functions are explicitly marked "NOT constant-time" |

- **Zero direct uses:** `ecdsa.c`, `poly1305.c`, `sha256.c`, `des.c`, `dhm.c`, `ecjpake.c`. `aes.c` only matches "round constants".
- Zero direct uses does not mean not constant time. ECDSA and similar code inherit whatever `bignum_core`/`ecp` guarantees, and I did not trace those call graphs.

The facility is a set of primitives used where the library has decided a secret matters. Its guarantee is per-function and documented in headers. Read the function's contract, not the module's.