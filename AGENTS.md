<!-- SPDX-License-Identifier: MIT -->
# AGENTS.md

Entry point for an agent doing one of two different jobs. They have almost nothing in common,
so pick first.

| you are… | read |
|---|---|
| **using clew** to answer questions about some repository | **[SKILLS.md](SKILLS.md)** |
| **changing clew itself** | the rest of this file |

---

# Working in this repository

## The gate is the contract

```bash
.venv/bin/pre-commit run --all-files
```

Always through pre-commit, never the hook tools directly — it owns the versions, flags and
ordering. Two failure modes this project has actually shipped:

- **Run the formatter BEFORE the gate, not after.** A formatter pass after a green gate is how
  1.0.33 shipped red.
- **A gate that reports success while checking nothing is worse than a red one.** Files skipped
  by `toolchain.toml` were logged at INFO while logging was pinned to WARNING, so `rc=0` came
  back with zero output. If you add a skip, print the count.

Never `--no-verify`. Never `@pytest.mark.skip` or `xfail` to move on.

## Python goes through the venv

`.venv/bin/python`, `.venv/bin/pip`, `.venv/bin/pre-commit`. Never bare `python`/`python3`/`pip` —
a system interpreter has different packages and pollutes the global environment.

## Doxygen comments are enforced, including `@version`

Every function carries a `## @brief` block and a docstring. **When you change a function's body,
bump its `@version`** — `clew guard` fails the commit otherwise, and it reads the `##` block's
version, not the docstring's. Say *why* it changed in a comment above the block; the history of a
function's reasoning is the point, not the number.

Complexity limits are enforced: cognitive complexity ≤ 15, returns ≤ 3. Refactor rather than
disable.

## Tests are specifications

A failing test means the code is wrong until proven otherwise. **RED first**: write the test,
watch it fail, then fix. This repository has caught itself four times writing a test that passed
before the fix existed — once in this release, where a progress-regression test only checked
final output and had to be rewritten to assert interleaving.

Two rules with teeth:

- **Never change a test to match broken behaviour.** Changing a *fixture* is sometimes right — if
  a test's example string happens to trip new behaviour while the property it guards is unchanged,
  fix the fixture and say so in a comment.
- **A test that cannot fail is a liability.** `test_fixture_fidelity` exists because a synthetic
  fixture missing a shipped table is "a licence to assert over a schema that does not exist."

## Absence is not emptiness

The rule this codebase returns to most often. A detector that cannot tell "nothing is there" from
"nobody looked" will eventually report the flattering one:

- an empty table means *we looked and found nothing*; an **absent** table means *this layer never
  ran*. Create tables unconditionally, even at zero rows.
- `not_indexed: []` reads as "nothing was missed". Drop the key instead.
- `end_line = 0` means *extent unknown* — never "covers nothing" and never "covers everything".
- `tool_calls = -1` means *unknown*, and must never be counted as zero.
- a `false` is a measurement and is always reported; a field that does not apply is **absent**.

## Adding an index layer touches seven places

Learned by missing them. A new harvest layer needs: a `vocabulary.py` stage constant *and* its
`STAGE` tuple entry *and* its rank; the module; `harvest_plan.py`'s field, constructor entry **and
`active()` list**; the `cli.py` stage call; the query model and its reader; plus
`tests/richdb.py` and `tests/test_vocabulary.py`'s schema fixture.

**`active()` is the one that bites.** A harvester omitted there still works — it silently
re-parses the whole tree instead of reading a warmed cache. `test_every_harvester_subclass_is_reachable_from_the_plan`
exists for exactly that.

## Measurements are claimed with a method or not at all

A number in a comment, a commit message or a requirement carries the target it was measured on
and how. "875 occurrences" and "875 lines" are different claims about the same grep, and a figure
whose method cannot be reproduced gets **removed rather than re-derived** — inventing a method to
justify a number is how the number stops being evidence.

## Security posture

Indexing a repository **runs that repository's code** by design — cargo compiles it, doxygen runs
with its Doxyfile as base text. Treat `clew index` as equivalent in trust to `cargo build` on that
tree, and read `docs/SECURITY.md` before touching the pipeline's subprocess surface. Every git
call goes through `gitenv.git_argv`; a target's own `.git/config` could otherwise execute commands.

## The acceptance harness

`acceptance/` measures clew against a shell-only agent. If you touch it, read
`acceptance/DESIGN.md` first — particularly that **the two arms' briefs must differ only in the
tool sentence**, and that a usage document goes to the *system prompt* rather than the brief for
that reason. Generation cannot be re-run cheaply; grading can, and is additive.
