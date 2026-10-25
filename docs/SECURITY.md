# Security model

What clew promises, what it does not, and what to report.

clew points a parser, a documentation generator and a build tool at a repository, then serves
what they found to a model that acts on it. Both halves of that sentence carry risk, and this
document states where the boundaries actually are rather than implying there are more of them
than there are.

The audit behind the 1.1.0 release worked from four positions: **A** — the indexed repository
is hostile; **B** — the MCP caller is hostile, or is an agent carrying a prompt injection;
**C** — the operator's configuration is wrong; **D** — the supply chain. The fixes it produced
are in the change log at the bottom. The non-guarantees below are the ones no fix delivers.

## What clew promises

These are the invariants the pipeline and the gate are built to hold. A violation of one is a
bug worth reporting:

- **Declared and stated scope stays inside the repository.** `index_scope.roots`,
  `kconfig.root`, `preprocessor.config_header`, every supplementary-document glob and every
  file-documentation path resolve first and are then refused if they land outside the
  repository root. A committed symlink pointing out of the tree is refused, not followed.
- **The Doxyfile gains no command-valued or file-reading directive from repository or caller
  input.** The target's own Doxyfile is base text; clew appends a forced block that wins by
  being last, neutralising every input filter, every generator that runs a program, every
  path that would let `@verbinclude` and its fourteen siblings inline a file, and symlink
  traversal.
- **No subprocess inherits a git or Kconfig override.** A repository's own `.git/config`
  cannot name a command git will run, in the pipeline or in the gate; a `Kconfig` is parsed in
  a minimal environment where `$(shell,…)` is refused and recorded rather than executed.
- **Every subprocess is bounded.** No call to git, cargo or doxygen can hang a build, a
  pre-commit run or a long-lived MCP server indefinitely.
- **Gate output and registry paths stay inside their roots.** The gate's full write path is
  validated before any directory is created; the registry refuses to delete outside its state
  root, resolving before it compares.

A test exists for each of these, and two of them — `tests/test_security_surface.py` and
`tests/test_packaging.py` — are structural: they assert the property over clew's own source
and packaging, so the next call site that breaks the rule is caught rather than the ones
already known.

## What clew does not promise

### 1. Indexing a repository runs that repository's code, by design

`cargo metadata` and `cargo doc` compile the target, which executes its `build.rs`, its
procedural macros and whatever its `.cargo/config.toml` directs. doxygen runs with the
target's own Doxyfile as base text. kconfiglib has a shell function. clew bounds these, scrubs
their environments and forces the settings that turn them into arbitrary-execution primitives
— but the tools themselves are the feature, and clew does not sandbox them.

**Treat `clew index <tree>` as equivalent in trust to `cargo build` on that tree.** There is
no sandbox and none is planned; a sandbox is the operator's to provide, with a container or a
restricted user.

### 2. The process environment is in scope

Subprocesses inherit the environment clew was started in. Run as the MCP plugin, that is the
editor's environment: `ANTHROPIC_API_KEY`, `GH_TOKEN`, `AWS_*`, `SSH_AUTH_SOCK` and whatever
else is exported there. clew scrubs the variables that change how git and kconfiglib behave,
because those are execution vectors. It does not and cannot scrub secrets in general — a
`build.rs` reads the environment it is given.

### 3. `clew.db` is as sensitive as the most sensitive file the build user can read

The database holds verbatim source bodies, comments, prose and configuration from everything
indexed. **Do not commit it and do not sync it.** A clew.db built over a tree containing
credentials contains those credentials.

### 4. clew is a prompt-injection carrier by construction

Its thesis is putting a third party's prose into a model's context with authority. A `@brief`,
a function body comment, a README chunk and a Kconfig `help` text are all attacker-controlled
on a hostile target, and they are served verbatim because serving them verbatim is the point.

The served `INSTRUCTIONS` frame repository text as data, and the prose corpora carry an
explicit provenance string. **Framing is not a filter.** It raises the cost of a naive
injection and does nothing against a determined one. A consumer that acts on indexed text
without review is trusting the indexed repository, and no amount of wording changes that.

### 5. `target` is not a security boundary

One server answers about every index on the machine. `target` selects which repository a query
reads; it is routing, not isolation, and any caller that can reach the server can name any
indexed repository. **A server's trust level is the union of every repository it has ever
indexed.** Separate trust domains need separate servers.

### 6. The gate is configured by the branch under test

`clew guard` reads `.clew.yaml` — including `guard:` — from the working tree, and runs inside
`git commit` as that user. Checking out an untrusted branch and committing is therefore an
execution event, with the same standing as running that branch's `Makefile`. The 1.1.0 audit
closed the specific path by which a branch's `.git/config` could make the gate run a command
of its choosing; the general position is unchanged.

### 7. No resource guarantees

Beyond doxygen's and cargo's timeouts and a cap on concurrent background builds, there is no
memory, disk or CPU bound. A repository can be large enough, or crafted enough, to exhaust any
of them. The timeouts are backstops against a hang, not a budget.

### 8. The supply chain, stated honestly

An adopter installing clew's pre-commit hook resolves clew's full dependency closure live from
PyPI. That closure includes `lang-parsing-substrate`, a single-maintainer 0.x wheel of roughly
38 MB of compiled Rust which parses every byte of every target repository in-process, with no
fallback parser and no verification by clew. clew pins its GitHub Actions and pre-commit hooks
by commit SHA and bounds its dependency versions, which narrows the window for a mutable-ref
substitution. It does not eliminate the position: a compromised release of a dependency is a
compromise of clew.

### 9. Nothing here is a vulnerability report

The nine positions above are the design. Reporting one back as a finding is useful only if it
comes with a case that the promise in the first section was broken.

## Reporting

Use GitHub's private vulnerability reporting on this repository. Include the position (A–D
above), the promise from the first section you believe is broken, and the smallest tree that
demonstrates it. A reproduction against a real `clew index` or `clew guard` run is worth more
than a reading of the source, because several of the plausible readings turn out to be closed
by a forced Doxyfile flag or a scrubbed environment that is not obvious locally.

## Security-relevant changes

### 1.1.0

The first security audit of the project. Positions A–D, 39 surviving findings, all fixed
before the tag. The ones an adopter should act on:

- **A repository's own `.git/config` could execute commands on every git call clew made**
  (critical). `core.fsmonitor` and its siblings are run as commands by git itself, so
  `git -C <root> ls-files` against a hostile tree executed attacker-chosen code. It needed no
  doxygen, no cargo and no Kconfig, it fired on the first git call of a build, and the same
  defect was present in the pre-commit gate — where it runs as the committing developer.
  **Anyone who indexed an untrusted repository with clew 1.0.39 or earlier should assume
  command execution was possible.**
- **A repository's Doxyfile plus `@verbinclude` could inline any readable file** into served
  documentation, labelled as that repository's own text. Closed by redefining the fourteen
  file-reading doxygen commands in the forced block; the cost is that an in-repo `@include` or
  `@snippet` is refused too, because doxygen resolves those itself and containment is not
  expressible through its configuration.
- **A `Kconfig` file ran commands.** `$(shell,…)` executes through kconfiglib; the parse also
  expanded the editor's environment into served `prompt` and `default` strings, and would
  import a repository-supplied `kconfigfunctions.py`. Now parsed in a minimal environment with
  a refusing `shell` installed through kconfiglib's own documented extension point, with
  refusals counted into `build_meta`.
- **Several committed-symlink and stated-path reads escaped the repository** — supplementary
  documents, file documentation, `kconfig.root`, `preprocessor.config_header`,
  `index_scope.roots`, doxygen's own traversal, and the gate's impact-report write path.
- **`index(action='cull', max_age_days=0)` destroyed every index on the machine.**
- **Every GitHub Action and pre-commit hook is now pinned by commit SHA**, including the only
  job that holds the publishing credential, which was pinned to a mutable branch ref.

The release also added this document, a root `SECURITY.md`, structural tests over clew's own
subprocess use and packaging, and private vulnerability reporting on the repository.
