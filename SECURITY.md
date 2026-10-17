# Security policy

**Reporting:** use [GitHub's private vulnerability
reporting](https://github.com/tvanfossen/clew/security/advisories/new) on this repository.
Please do not open a public issue for a suspected vulnerability.

**Before reporting, read [`docs/SECURITY.md`](docs/SECURITY.md).** It states what clew
promises and — more usefully — what it does not. The most important item: **indexing a
repository runs that repository's code, by design.** `cargo` compiles the target, `doxygen`
runs with the target's own Doxyfile as base text, and clew does not sandbox either. Treat
`clew index <tree>` as equivalent in trust to `cargo build` on that tree. The same document
explains why `clew.db` is as sensitive as the most sensitive file the build user can read, why
clew is a prompt-injection carrier by construction, and why one MCP server's trust level is
the union of every repository it has ever indexed.

A report is most useful when it names which of the promises in that document's first section
is broken, and includes the smallest tree that demonstrates it against a real `clew index` or
`clew guard` run.

**Supported versions:** the latest release. clew is pre-1.x in practice — fixes land on the
current minor rather than being backported.
