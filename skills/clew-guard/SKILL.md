---
name: clew-guard
description: Use when a commit is refused by the clew-guard pre-commit hook, or when editing a documented function in a repository that runs it. Covers the four refusal classes — missing @version bump, missing @brief block, missing @req coverage, and cognitive complexity — and the conventions the error messages do not state.
---

# clew guard

A pre-commit gate that refuses a commit whose doxygen comments have fallen behind the code.
It runs as the `clew-guard` hook. You will meet it when you edit a documented function.

## It bumps the `##` block, not the docstring

This is the one that costs people a second attempt. A function carries two version numbers:

```python
## @brief Read one file's documentation.
## @version 3          <-- the guard reads THIS one
def doc_for(path: str) -> str:
    """...
    @version 3         <-- and not this one; keep them equal anyway
    """
```

`Function 'X' body changed but @version was not updated` means the `##` block above the `def`.
Bump both, so a reader of either is not misled.

## Say why, above the number

The point of the version is the history of the function's reasoning, not the integer. Put the
reason in a comment above the block:

```python
## v4: the join is on basename now — a build file writes ${VAR}/error.c and the index holds
## library/error.c, so neither string contains the other.
## @version 4
```

A bump with no reason passes the gate and loses the thing the gate exists to preserve.

## What it refuses

Its messages, verbatim:

| message | what it wants |
|---|---|
| `Function 'X' body changed but @version was not updated` | bump the `##` block's `@version`, with a reason |
| `Function 'X' has no doxygen comment` | a `##` block above the `def` |
| `Function 'X' doxygen missing @brief tag` (also `@return`, `@version`) | add the missing tag |
| `Function 'X' has no @req tag ... and no exemption (@callback, @dg_internal, @utility)` | a `@req REQ-...` id, **or** one of those three |
| `Unknown tag @X in f()` | a typo, or a tag this repo's config does not declare |
| `File-level doxygen missing X tag in 'path'` | the file's own header block |

Pick the exemption that is true: `@dg_internal` for a private helper, `@utility` for a shared
one with no requirement behind it, `@callback` for something a framework calls. Tagging a
function `@dg_internal` to silence the gate when it is part of the public surface is the failure
the coverage check exists to catch.

**Complexity is not this gate.** `cognitive complexity` and `max returns` come from a separate
hook (`knots`), and refactoring is the answer there too — but do not go looking in the guard's
config for them.

## Run it yourself before committing

```bash
.venv/bin/pre-commit run clew-guard --all-files     # or: clew guard validate
```

Through pre-commit, not the tool directly — pre-commit owns the version, the flags and the
ordering. The same gate is `clew guard` on the CLI.

## Do not bypass it

No `--no-verify`. No disabling the complexity check for a function that exceeds it. If a limit
is genuinely wrong for a case, that is a conversation with the repository's owner, not a flag.

## Configuration

The `guard:` section of the repo's `.clew.yaml`. A repo migrating from the old standalone tool
may still have `.doxygen-guard.yaml`; it is no longer read — move its contents under `guard:`.
Full reference: `docs/GUARD.md`.
