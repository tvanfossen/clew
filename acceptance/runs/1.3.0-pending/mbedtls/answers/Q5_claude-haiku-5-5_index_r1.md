## Short answer

Constant-time in mbedtls is a convention enforced by code structure, not by the compiler. Branch-free arithmetic keeps secrets out of `if`s, and an empty inline-asm barrier stops the optimizer from re-introducing them. Hand-written assembly covers the hot primitives on four architectures. Everything else falls back to plain C that is only *observed* to be constant-time. Nothing in the build fails when the fast path is missing. Actual verification is dynamic and happens in test builds only.

## Instruction-level enforcement

The public-facing layer is `mbedtls_ct_*` in `library/constant_time_impl.h`, with types and `MBEDTLS_CT_TRUE`/`MBEDTLS_CT_FALSE` in `constant_time_internal.h`.

- **Condition type.** A condition is an all-ones or all-zeros machine word (`MBEDTLS_CT_TRUE` / `MBEDTLS_CT_FALSE`), not a 0/1 `int`. Its width is 32 or 64 bits, chosen from `SIZE_MAX` and `MBEDTLS_HAVE_INT64`.
- **Optimizer barrier.** `mbedtls_ct_compiler_opaque(x)` is an empty `asm volatile ("" : [x] "+r" (x))`. The compiler must treat the value as unknown, so it cannot prove a condition constant and fold a branch.
- **Mask generation.** `mbedtls_ct_bool(x)` turns any non-zero `x` into an all-ones mask. On AArch64 it is `neg / orr / asr`; on x86-64 it is `mov / neg / or / sar`; on ARM32 it is `negs / orrs / asrs`.
- **Selection.** `mbedtls_ct_if(c, a, b)` is `(a & c) | (b & ~c)`, also in hand-written asm on the same four targets. Comparisons such as `mbedtls_ct_uint_ne/eq/lt/ge` are built on `bool` and `if`.
- **Memory compare.** `mbedtls_ct_memcmp` (`library/constant_time.c:67`) reads both buffers through `volatile` pointers so the loop cannot exit early. It XOR-accumulates the differences and never branches on data. It is constant with respect to the data, but not with respect to `n`. On 32-bit ARM and AArch64 it uses unaligned volatile word loads.

What this does **not** guarantee: the compiler can still emit a secret-dependent branch in the code around these calls, and nothing here controls the CPU's microarchitecture (cache, division timing). The barrier only stops the optimizer from *knowing* the value.

## What happens on an unsupported compiler

Selection is decided at preprocessing time in `constant_time_impl.h:40-52`:

| Situation | `MBEDTLS_CT_ASM` | Arch fast path | What you get |
|---|---|---|---|
| `MBEDTLS_HAVE_ASM` on, GNU-compatible, ARM/AArch64/x86/x86-64 | defined | yes | Hand-written mask/select asm |
| `MBEDTLS_HAVE_ASM` on, GNU-compatible, other arch (RISC-V, MIPS, …) | defined | no | Generic `"+r"` barrier; `bool`/`if` in C arithmetic |
| `MBEDTLS_HAVE_ASM` off, or MSVC / IAR / armcc5 | not defined | no | `x ^ mbedtls_ct_zero` where `mbedtls_ct_zero` is a `volatile` global; all C arithmetic |

There is **no `#error`** for the last two rows. The C fallback's own comment (`constant_time_internal.h:55-59`) says it "has been observed to be constant-time on latest gcc, clang and MSVC as of May 2023". That is an observation about compiler output, not a guarantee. A future compiler could regress it silently.

One related trap: `check_config.h:250` rejects `MBEDTLS_HAVE_ASM` combined with MemorySanitizer. So the MSan constant-flow build necessarily runs the C fallback, not the shipped assembly.

## How far it reaches

I counted `mbedtls_ct_*` call sites in `library/`: about 238 across 27 files. The largest users:

- `rsa.c` (25), `bignum_core.c` (21), `bignum.c` (18), `cipher.c` (20), `ssl_msg.c` (17), `base64.c` (10)
- `ssl_tls12_server.c` (7), `nist_kw.c`, `psa_crypto.c`, `ccm.c`, `gcm.c`, `cmac.c`, `chachapoly.c`, `ssl_cookie.c`, `bignum_mod_raw.c`

Concrete consumers from the dossier callers: `mbedtls_rsa_rsaes_oaep_decrypt`, `mbedtls_ssl_decrypt_buf` (record padding check), `mbedtls_mpi_core_random`, and `mbedtls_mpi_core_check_zero_ct` / `mbedtls_mpi_core_lt_ct`. The public `mbedtls_mpi_lt_mpi_ct` in `bignum.h` exposes the comparison to applications. `mbedtls_mpi_gcd_modinv_odd` wraps a constant-time GCD/inverse.

Limits of that reach:

- **ECC scalar multiplication is not in the list.** `ecp*.c` does not appear among the files using `mbedtls_ct_*`. I did not read `ecp.c`, so I can't say from this what it uses instead. The third-party `p256-m` has its own `MUL64_IS_CONSTANT_TIME` gating, and the bundled Everest/HACL code uses its own helpers.
- **It is opt-in per call site.** Only code that calls these helpers gets the property. The facility does not analyse other code.

## How it is tested

- `MBEDTLS_TEST_CONSTANT_FLOW_VALGRIND` and `_MEMSAN` are documented in `mbedtls_config.h:2109-2142`. The Valgrind one is the one the CI runs: `test_with_valgrind_constant_time` (`tests/scripts/components-configuration-crypto.sh:25`) runs `tests/suites/*constant_time*.data` under memcheck. Memcheck flags secret-dependent branches as uninitialised-value use.
- The implementation of those hooks lives in the `framework/` submodule (`constant_flow.h`). **That submodule is empty in this checkout**, so I could not read the Valgrind hook itself. This is a limit of this answer, not of the library.

## Summary

- **Enforced:** branch-free masks in asm on four architectures, plus an optimizer barrier everywhere a GNU compiler is used.
- **Not enforced:** a compile-time or runtime check that the fast path is active. On MSVC, IAR, armcc5, or a build without `MBEDTLS_HAVE_ASM`, the library silently uses C code that is only observed to be constant-time.
- **Verified by:** Valgrind memcheck on asm builds, and MSan on the C-fallback build.
- **Reach:** about 27 library files and the RSA-OAEP, record-padding, and MPI paths. Not demonstrably ECC scalar multiplication.