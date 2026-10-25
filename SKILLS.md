<!-- SPDX-License-Identifier: MIT -->
# Using clew well

clew answers questions about a repository from a prebuilt index, through three MCP tools:
`dossier`, `search` and `index`. This document is how to use them so they cost less than reading
the source — which is the only reason to use them at all.

Every rule here came from watching real runs get it wrong, and where clew loses, that is stated
too. **No figures live in this document.** The measurement and its disclosed defects have exactly
one home — `acceptance/runs/<date>/` — because a number copied into a usage document has no owner
and no test, and goes stale the next time the grid runs.

---

## 1. Ask for everything you need in one call

`dossier` takes a **list**. Up to eight subjects, one reply, one round trip:

```
dossier(subject=["mbedtls_ssl_handshake", "mbedtls_ssl_setup", "mbedtls_ssl_init"])
```

**Most real calls pass a single subject.** That is the single most common way to use these tools
badly: every declined batch is a round trip bought for nothing, because the reply for three
subjects costs barely more than the reply for one.

So: **collect the names first, then fetch them together.** If a reply names five callers you want
to inspect, that is one call, not five.

## 2. Use `depth` instead of walking by hand

For "what does this reach" or "what reaches this", `dossier` walks the graph itself:

```
dossier(subject="mbedtls_ssl_read", depth=3, direction="back")
```

**`depth > 1` is almost never used.** Nearly every walk gets re-implemented one call at a time
instead. `direction="back"` is upstream, `"forward"` downstream, and the reply's `chain` is the
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

**The index alone answers less completely than a shell-only agent, and costs meaningfully less to
run. Given both, an agent answers about as completely as with a shell alone, still cheaper.**

So clew is a cheaper way to be precise about named things, and not a replacement for reading a
repository. Used as in §1–§4 it should cost fewer round trips than grep; used one symbol at a
time it costs more.

**For the figures, read `acceptance/runs/<date>/RESULTS.md` and the `KNOWN-DEFECTS.md` beside
it** — never a number quoted anywhere else, including here. The published result is PROVISIONAL
and its defects are disclosed with the direction each one moves the numbers; a headline copied out
of that pair loses the disclosure that makes it honest.
