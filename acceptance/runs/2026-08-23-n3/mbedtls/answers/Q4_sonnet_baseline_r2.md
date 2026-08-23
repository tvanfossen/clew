This is a single, self-contained explanatory question, not multi-step work — a todo list wouldn't add anything here. I now have everything needed to answer.

## How a negative error code becomes a string

**1. The code itself is a bitfield, not an opaque number.**
`include/mbedtls/error.h:17-91` documents the 16-bit layout: sign bit, 3-bit high-level module ID, 5 bits of module-dependent detail, 7-bit low-level module error. A returned value is frequently the *sum* of a high-level code and a low-level code, glued together by `mbedtls_error_add()` / the `MBEDTLS_ERROR_ADD(high, low)` macro (`error.h:107-154`) — e.g. an `MBEDTLS_ERR_PK_...` (high-level) combined with an `MBEDTLS_ERR_ASN1_...` (low-level) when a PK operation fails because of a low-level ASN.1 parse error.

**2. `mbedtls_strerror()` splits it back apart.** In `library/error.c:792-860`:
- Negates `ret` if negative.
- Masks `ret & 0xFF80` → looks it up via `mbedtls_high_level_strerr()`.
- Masks `ret & ~0xFF80` → looks it up via `mbedtls_low_level_strerr()`.
- Concatenates `"<high> : <low>"` into the caller's buffer (truncating safely, always NUL-terminating).
- Special case: `MBEDTLS_ERR_SSL_FATAL_ALERT_MESSAGE` returns early without a low-level suffix.

**3. The two lookup functions are giant `switch` statements** (`error.c:174-535` and `537-790`), each `case` guarded by the module's `#if defined(MBEDTLS_xxx_C)` so the string table only contains strings for modules actually compiled in. Each case does `case -(MBEDTLS_ERR_FOO_BAR): return "FOO - human text";`.

**Critically: nobody hand-writes those `case` blocks.** The block is fenced by `/* Begin Auto-Generated Code. */` … `/* End Auto-Generated Code. */` and is produced entirely by `scripts/generate_errors.pl`.

## What a contributor actually does to add a new error code

1. **Define the macro** in the appropriate `include/mbedtls/*.h`, following the existing layout rules in `error.h`'s comment block (pick an unused code point in the low-level or high-level numeric range for that module — this is the part a human has to get right, since the generator just harvests whatever's declared). Attach a doxygen comment either immediately before (`/**`) or immediately after (`/**<`) the `#define` — the generator's regex (`generate_errors.pl:59-71`) requires exactly one of the two, and dies if it finds both or neither.
2. If it's a **brand-new module** (not an existing one), add its name to `@low_level_modules` or `@high_level_modules` array at the top of `generate_errors.pl:36-43` — otherwise the script exits with `"Error: Do not know how to handle: MODULE\n"` (`generate_errors.pl:139-143`).
3. **Run the generator**: `scripts/generate_errors.pl` (no args, run from repo root). It rescans every header in `include/mbedtls/*.h`, extracts all `MBEDTLS_ERR_*` defines + their comments, groups them by module, and rewrites `library/error.c` from the template `scripts/data_files/error.fmt`, regenerating the `#include` list, the high-level switch, and the low-level switch, and dies on a duplicate numeric code (`error_codes_seen` check, line 110-111).
4. **Do not hand-edit `library/error.c`'s generated block** — `tests/scripts/check-generated-files.sh:135` checks that `library/error.c` matches what `generate_errors.pl` would currently produce, so a manually-added `case` (or a forgotten regen) fails CI.
5. Commit both the header change and the regenerated `error.c` together.

So the round trip is: define macro + doxygen comment → (if new module) register it in the generator's module list → run `generate_errors.pl` → regenerated `error.c` gives `mbedtls_strerror()` a new `case` to match, and CI's generated-files check is what actually enforces step 3 wasn't skipped.

One caveat for accuracy: I answered this by reading `error.h`, `error.c`, and `generate_errors.pl` directly rather than through `clew`'s MCP tools — they weren't available in this session (no `mcp__clew__*` tools were exposed), which this repo's own instructions flag as a finding worth recording rather than silently working around.
