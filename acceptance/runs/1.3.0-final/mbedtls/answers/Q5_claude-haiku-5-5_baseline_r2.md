The facility is `library/constant_time_impl.h` (declarations in `constant_time_internal.h`, public API in `include/mbedtls/constant_time.h`). It is a set of branch-free primitives, and nothing in the build proves the generated machine code is branch-free. The only verification is dynamic testing on the paths the tests exercise.

**How it is enforced at the instruction level**

- **Hiding values from the optimiser.** `mbedtls_ct_compiler_opaque()` wraps values in an empty `asm volatile("" : [x] "+r"(x))` on GNU-asm targets. The compiler cannot prove a condition's value, so it cannot turn a mask into a branch. Without asm it XORs with a `volatile` global, `mbedtls_ct_zero`, which the compiler must assume could change.
- **Masks instead of comparisons.** `mbedtls_ct_bool(x)` turns any non-zero value into an all-ones mask using neg/or/shift. `mbedtls_ct_uint_lt` derives its result from the sign bit of a subtraction. `mbedtls_ct_if` selects with `(c & a) | (~c & b)`. The `_if_else_0` and `memcpy_if` variants work the same way.
- **Hand-written asm for four ISAs.** AArch64, 32-bit Arm/Thumb, x86-64 and x86-32 each have explicit instruction sequences for the core ops (`ct_bool`, `ct_if`, `ct_uint_lt`). This is the strongest guarantee in the design.
- **Full-width memory access.** `mbedtls_ct_memcmp` reads every byte through `volatile` pointers and ORs the differences, so it has no early exit. `mbedtls_ct_memcpy_if` always touches every byte of both sources. The ECP comb table lookup (`ecp_select_comb`, `library/ecp.c:2010`) reads the whole table and conditionally assigns each entry.

**How the test side checks it**

`tests/suites/test_suite_constant_time.function` marks secret inputs with `TEST_CF_SECRET` and `TEST_CF_PUBLIC`. Under Valgrind memcheck or MSan, marked secrets are treated as uninitialised memory, so any secret-dependent branch or address shows up as an uninitialised-value error. The CI components are in `tests/scripts/components-sanitizers.sh`. Caveats:
- The macros live in `framework/tests/include/test/constant_flow.h`. The `framework/` directory is empty in this checkout, so I could not read their bodies.
- This only catches leaks on the inputs the tests run. It does not inspect the disassembly.

**What happens on a compiler that cannot support it**

Selection is a preprocessor chain in `constant_time_impl.h`.
- `MBEDTLS_CT_ASM` is defined only when `MBEDTLS_HAVE_ASM` is set and `__GNUC__` is available (armcc5 is excluded).
- Within that, the per-ISA macros pick the asm bodies. Any other GNU target (for example RISC-V or Xtensa) gets `MBEDTLS_CT_ASM` for the opaque barrier but falls through to the C bodies for the primitives.
- Everything else, including MSVC, IAR, or a build with `MBEDTLS_HAVE_ASM` undefined, uses the plain C fallback and the `volatile mbedtls_ct_zero` barrier.

There is no `#error` for unsupported targets. The degradation is silent. The header's own comment says the C fallback has "been observed to be constant-time" on recent gcc, clang and MSVC as of May 2023. That is an observation, not a guarantee. The `valgrind_constant_flow_no_asm` component exists to exercise the C path.

**How far it reaches**

Occurrence counts of `mbedtls_ct_` in `library/`, which measure usage, not coverage of every secret path:

| Area | Count | Notable use |
|---|---|---|
| `bignum_core.c`, `bignum.c` | 32, 26 | Comparisons; `mbedtls_mpi_safe_cond_*` used by ECP |
| `rsa.c` | 37 | PKCS#1 v1.5 unpadding via `mbedtls_ct_memmove_left` |
| `cipher.c` | 30 | CBC padding handling |
| `ssl_msg.c` | 24 | `mbedtls_ct_hmac` for CBC record MAC verification |
| `base64.c` | 21 | Decoding |
| `psa_crypto*.c` | 9 + 4 + 1 | PSA paths |
| `ssl_tls12_server.c` | 8 | Server-side key exchange |
| `nist_kw.c` | 4 | `mbedtls_ct_memcmp_partial` |

ECP itself has no direct `mbedtls_ct_` calls. It gets its constant-time behaviour from `mbedtls_mpi_safe_cond_assign` and `mbedtls_mpi_safe_cond_swap`, which run on the bignum layer. Three ECP entry points are explicitly documented as not constant-time: `mbedtls_ecp_mul_shortcuts` (`ecp.c:2734`, short Weierstrass only), `mbedtls_ecp_muladd_restartable` (`ecp.c:2769`) and `mbedtls_ecp_muladd` (`ecp.c:2873`). The "constant op_count" self-tests check operation counts, not timing.

Outside the files above, I found no constant-time references in the hash, DES, Camellia, ARIA, ChaCha20 or Poly1305 sources. For AES I checked for constant-time or cache references and found none, but I did not read its table-lookup code, so I cannot say whether it is table-based. Treat the facility as covering the bignum, RSA-padding, CBC-MAC, ECP-table and tag-comparison paths. It is not a library-wide property.

*Note: a PostToolUse hook message appended to one tool result suggested other tools (`dossier`, `search`) that are not in my toolset. I ignored it and used the repository files directly.*