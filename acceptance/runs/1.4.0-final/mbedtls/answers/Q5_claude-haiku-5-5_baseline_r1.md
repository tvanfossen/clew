The short answer: mbedtls does not enforce constant time in any strict sense. It uses a small set of primitives that are written to be branch-free, pins the sensitive ones in inline assembly on a few architectures, and then checks the result with MemorySanitizer and Valgrind in CI. On a compiler without the assembly path, it silently falls back to plain C and emits no warning. The facility is used in about 27 library files, but most of the library still uses ordinary branches and `memcmp`.

**1. How it works at the instruction level**

The public API is one function, `mbedtls_ct_memcmp` (`include/mbedtls/constant_time.h`). Everything else is internal, in `library/constant_time_internal.h` and `library/constant_time_impl.h`. Secret values are carried as `mbedtls_ct_condition_t`, a full-width mask that is all ones for true and all zeros for false, and are combined with `_if`, `_eq`, `_lt` and similar helpers. There are three mechanisms:

- **Mask arithmetic.** `mbedtls_ct_bool(x)` turns any value into a mask without a branch. On x86-64 the asm is `neg`/`or`/`sar`, so the result depends on the sign bit of `x | -x`. `mbedtls_ct_if` selects with `and`/`not`/`and`/`or`.
- **Opacity.** `mbedtls_ct_compiler_opaque(x)` is an empty asm with a `+r` constraint (`constant_time_impl.h`). It stops the optimiser from proving that a mask is 0 or all-ones and turning it back into a branch. Without asm it XORs with a `volatile` zero (`library/constant_time.c:23`).
- **Volatile reads.** `mbedtls_ct_memcmp` reads both buffers through `volatile` pointers so the compiler cannot exit early once `diff` is nonzero. It XORs the bytes and folds the result into a value that is nonzero iff the buffers differ.

Assembly versions exist for ARM 32-bit/Thumb, AArch64, x86-64 and i386 (`constant_time_impl.h:40-60`). They are enabled only when `MBEDTLS_HAVE_ASM` is defined, the compiler is GNU-compatible (GCC or Clang, or ARMCC 6+), and the target matches one of those architectures. `MBEDTLS_HAVE_ASM` is on by default in `mbedtls_config.h:52`.

**2. Compilers that can't support it**

There is no failure mode. `MBEDTLS_CT_ASM` simply stays undefined and the C fallback is used. Two `#error` checks exist but they are not about capability. One rejects `MemorySanitizer` combined with assembly (`check_config.h:250`), and one rejects `int` narrower than 32 bits in `mbedtls_ct_memcmp`. A compiler such as MSVC, IAR, or an older ARMCC gets the C path with no diagnostic.

The header says the C path has been "observed to be constant-time on latest gcc, clang and MSVC as of May 2023." That is an observation, not a guarantee. `SECURITY.md:109` is candid about it: compilers can introduce timing side channels, "this prevention may not be complete", and the project will treat exploitable leaks only at common `-O2`/`-Os` levels.

**3. What the assembly does not protect against**

The asm stops the compiler from reasoning about values. It does not control the CPU. Cache timing, variable-latency instructions, and spills that the compiler places outside the asm block are all out of scope. The compiler also remains free to reorder or copy values around the asm.

**4. How it is tested**

The checks live in `tests/scripts/components-sanitizers.sh`:

- `MBEDTLS_TEST_CONSTANT_FLOW_MEMSAN` builds with Clang MemorySanitizer. Secret inputs are marked uninitialised, so any secret-dependent branch or index is reported.
- `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` runs `make memcheck` on the same idea.
- `test_suite_constant_time` also runs with the asm path under Valgrind. Under MSan or Valgrind the default is the plain C path, so the asm is tested separately.

These tests annotate secrets with `TEST_CF_SECRET` and `TEST_CF_PUBLIC` from `test/constant_flow.h`. That header lives in the `framework/` submodule, which is not checked out in this copy, so I could not read it. The tests are the only way the claim is verified, and they only cover the code paths the suites exercise.

**5. How far it reaches**

`mbedtls_ct_` symbols appear in about 27 library files. The heaviest users are:

| File | Use |
|---|---|
| `rsa.c` | PKCS#1 v1.5 decryption and padding checks, signature verify compare |
| `bignum_core.c`, `bignum.c`, `bignum_mod_raw.c` | Constant-time bignum operations |
| `ssl_msg.c` | CBC padding and record MAC check, with `memcpy_if` and `memcmp` |
| `cipher.c` | AEAD tag compare |
| `base64.c` | Constant-flow decode |
| `psa_crypto*.c` | Hash, MAC and signature compare |
| `nist_kw.c` | Unwrap integrity check |
| `gcm.c`, `ccm.c`, `chachapoly.c`, `cmac.c` | Tag compare (one call each) |

Outside that set, the library uses plain `memcmp` in about 131 places. I did not classify them all. Many are self-tests or ASN.1 OID matching, where no secret is involved. The ChangeLog (entry around line 14) states that RSA PKCS#1 v1.5 decryption was made constant-time in its error handling but "remains inherently dangerous", so the facility does not make that primitive safe to use.

The short version: the assembly is a best-effort compiler barrier on four architectures, the C fallback is a plausible but unguaranteed alternative, and MSan/Valgrind testing is what gives confidence. The coverage is targeted at specific secret-handling paths rather than the whole library.