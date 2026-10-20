<!-- SPDX-License-Identifier: MIT -->
# Using clew well

clew answers questions about a repository from a prebuilt index, through three MCP tools:
`dossier`, `search` and `index`. This document is how to use them so they cost less than reading
the source — which is the only reason to use them at all.

**Every number below was measured**, on a 90-cell acceptance grid over Mbed-TLS and a C++
service, against the same questions answered by an agent with only shell tools. Where clew loses,
that is stated too.

---

## 1. Ask for everything you need in one call

`dossier` takes a **list**. Up to eight subjects, one reply, one round trip:

```
dossier(subject=["mbedtls_ssl_handshake", "mbedtls_ssl_setup", "mbedtls_ssl_init"])
```

**Measured: 69% of real dossier calls passed a single subject.** That arm then spent 11.8 dossier
calls per question where roughly 6 would have done, and finished with *more* round trips than the
shell-only agent — while using 30% fewer output tokens per call. The index was cheaper per
question asked and lost the advantage by asking one at a time.

So: **collect the names first, then fetch them together.** If a reply names five callers you want
to inspect, that is one call, not five.

## 2. Use `depth` instead of walking by hand

For "what does this reach" or "what reaches this", `dossier` walks the graph itself:

```
dossier(subject="mbedtls_ssl_read", depth=3, direction="back")
```

**Measured: 3% of calls used `depth > 1`.** The other 97% re-implemented the walk one call at a
time. `direction="back"` is upstream, `"forward"` downstream, and the reply's `chain` is the
bounded causal path.

## 3. `search` finds names; it is not where you read answers

Use `search` when you do not have a name yet. Then batch the fetch (§1).

- `corpus="symbols"` (default) — functions, variables, macros, types
- `corpus="files"`, `"config"`, `"locks"`, `"threads"` — **enumerate a whole layer**
- `corpus="prose"` — the repository's own markdown, full text

**Matching is a conjunction**: every whitespace-separated token must appear in one searchable
unit. Two distinctive words beat a phrase. `search(text="handshake step")` finds less than
`search(text="handshake")`.

## 4. Enumerate the layer before walking symbols

Questions of the form *"which files/directories do X"* are answered by a layer enumeration, not by
visiting symbols one at a time. `corpus="files"`, `"threads"`, `"locks"` and `"config"` each
return the whole layer in one call.

**Measured: three of the eleven marks the index-only agent lost were tree-wide aggregations whose
data the index already held.** It had the rows and did not roll them up. This is the cheapest
quality gain available to a consumer of clew.

## 5. Read the reply's own metadata before concluding anything

- **`target`** — which repository answered. One server serves many.
- **`not_searched`** — parts of a split index that were not read. **An empty result with a
  `not_searched` list is not "absent"**; it is "not looked for here".
- **`staleness`** — present if and only if the index is older than the source. Do not open a
  session with `index(action='status')`: every reply already carries this.
- **`anchor_mismatch: true`** — the file changed since the build, so those line numbers are no
  longer that symbol's.
- **`truncated: true`** — raise `max_body_lines` rather than making a second call.
- **`provenance: 'ast'`** — recovered from source doxygen never emitted. An empty brief there
  means *unparsed*, not *undocumented*.

A field that does not apply is **absent**, not empty. `false` is a measurement and is always
present.

---

## What clew cannot answer, and when to stop asking it

Reading the source after the index names the file is **the intended path, not a failure**. These
are the cases where it is the only path. All four were measured as losses on the grid.

**Files outside the indexed set.** The index covers 21 languages. A Perl generator, a Makefile, a
CI config, a `.fmt` data file — none are in it. On Mbed-TLS, `scripts/generate_errors.pl` has
**zero** index rows, so *"what is `library/error.c` generated from"* is unanswerable from the
index. Build tooling is invisible; go read it.

**Negative space — what a build deliberately leaves OFF.** clew indexes what exists. From 1.1.0
`config_defaults` records commented-out `#define`s in configuration headers, and
`dossier`'s gates carry a `default_state`. Beyond that, "this pointer has no default and will
fail" is a fact about an absence; the index will not volunteer it.

**Aggregate or distributional claims.** "Used broadly across the library" is a judgement over
counts. The index gives you the counts (§4); the judgement is yours.

**Threads whose entry point has no name.** The thread layer records a spawn when it can resolve a
named entry function. A `std::thread([]{ ... })` doing inline work yields no entry and is **not
recorded**. If a thread question matters, confirm against the source.

---

## The honest summary

On the 1.1.0 grid, the index alone scored **17.9 points below** a shell-only agent on answer
completeness, while using **29.8% fewer output tokens** and **18.4% less wall time**. The same
agent given both the index and a shell scored **4.1 points above** shell-only.

So clew is a cheaper way to be precise about named things, and not a replacement for reading a
repository. Used as in §1–§4 it should cost fewer round trips than grep; used one symbol at a
time it costs more.
