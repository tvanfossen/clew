<!-- SPDX-License-Identifier: MIT -->
# C++

| | |
|---|---|
| front end | **doxygen** (sqlite3 output) **+ tree-sitter-cpp** |
| requires | `doxygen` built with sqlite3 support; `gcc` |

Everything in [`C_INTEGRATION.md`](C_INTEGRATION.md) applies — scope keys, macro blindness,
declared conventions, requirements. This file is only what C++ adds.

## Threads

`std::thread` and `std::jthread` are treated as language primitives, exactly like
`pthread_create`, and need no declaration.

A lambda thread entry resolves to its callee when the lambda body is a **single call**. A
multi-call lambda body stays fail-closed with **no thread row** rather than guessing an entry —
a bounded limitation, deliberately, not a bug.

## Classes and dispatch

Virtual dispatch is not discovered automatically. A `trait`-style interface/implementor pairing is
resolved when an owner **declares** it:

```yaml
dispatch:
  interfaces:
    - interface: MyInterface
      implementors: [ConcreteA, ConcreteB]
```

A declared edge earns `resolved` only when the override is unambiguous **and** the incoming edge
is non-fuzzy — both the reachability and thread walks traverse `resolved`, so a fuzzy premise
would propagate as fact.

A qualified entry that does not resolve to its own class stays NULL rather than borrowing another
class's identity.

## Overloads

When a bare name maps to more than one signature, `dossier`, `search` and `chain_trace` return a
capped `candidates` list, so a bare name never silently traces an arbitrary overload. It is empty
on unambiguous names.

**`candidates` disambiguates the symbol's identity, not its edges.** `callers`/`callees` resolve
by NAME, so several unrelated file-private helpers sharing a name collapse into one node and their
edges merge — reported with full confidence, because every corroborating layer also resolves by
name. Do not trust the neighbour lists for a common file-private helper name.

## Grammar traps worth knowing

Two shapes cost real defects here and are handled, but they explain otherwise-baffling output:

- `W(W&&) = default;` parses as a `function_definition` whose `= default;` sits where a body
  would. The discriminator is whether the node has a `body` field.
- A method defined **inside** its class body is named `field_identifier`, not `identifier`.
  Accepting only `identifier` silently skips every in-class method definition.
- A reference-returning definition (`const T& f()`) nests under a `reference_declarator` that does
  not expose its inner declarator under the `declarator` field.

## Templates

doxygen's xref pass does not record a macro used in **non-type template argument position** —
`std::array<Row, MACRO>` emits no xref where `int buf[MACRO]` does. Those references are recovered
from the AST and written with `context='ast'`, so the two layers stay distinguishable by a plain
`WHERE`.
