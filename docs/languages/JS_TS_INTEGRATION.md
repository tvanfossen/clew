<!-- SPDX-License-Identifier: MIT -->
# JavaScript and TypeScript

| | |
|---|---|
| front end | **clew's own parse** (`clew/synth.py`), from lang-parsing-substrate's JavaScript, TypeScript and TSX grammars |
| extensions | `.js` `.mjs` `.cjs` `.jsx` `.ts` `.mts` `.cts` `.tsx` |
| requires | nothing beyond clew. A repo with no C, C++ or Python does **not run doxygen** |
| provenance | rows carry `dg_source = 'parse'` |

doxygen has no JavaScript or TypeScript parser, so clew builds these files' rows itself, in the
same tables doxygen and rustdoc fill. Every downstream layer (call edges, reachability,
requirements, search, `dossier`) then works on them unchanged. In a mixed repo, doxygen
indexes the C/C++/Python and this front end adds the JS/TS to the same index.

## What becomes a symbol

| Source | Row |
|---|---|
| `function f() {}`, `function* g() {}` | `memberdef` function |
| a class method, including `static` | `memberdef` function, `member` of its class |
| `const f = () => ...`, `const f = function () {}` | `memberdef` function named `f` |
| a class field `f = () => ...` | `memberdef` function, `member` of its class |
| `class`, `abstract class`, `interface`, `enum` | `compounddef` (`class` / `interface` / `enum`) |
| `extends` / `implements` a class or interface defined in the repo | `compoundref` (only when the name is unique) |

Names are qualified by module path, the way doxygen qualifies Python:
`src/util/strings.ts` → `definition = src.util.strings.Formatter.trim`,
`scope = src.util.strings.Formatter`, compound `src::util::strings::Formatter`. A TypeScript
return annotation is the `type`.

**Not symbols:** anonymous functions (callbacks, IIFEs, `export default function () {}`), and
functions nested inside another function. Their calls are attributed to the enclosing named
function, which is where a reader looks for them. TypeScript signatures without a body
(overloads, `declare`, interface members) are declarations, not definitions.

## JSDoc

The JSDoc block above a definition (or above the `export` / `const` around it) becomes the
description, rendered the way doxygen renders its own:

- the summary (an explicit `@brief`, else the first paragraph) is the brief;
- the remaining prose is the detail;
- `@version` becomes the version `dossier` reports;
- every other tag (`@req`, `@param`, `@returns`) is kept as literal text, so `@req` links
  requirements exactly as it does in C.

A file-level doc is a leading JSDoc block carrying `@file`, `@fileoverview`, `@module` or
`@overview`. A shebang or `'use strict'` above it is skipped. A leading block without one of
those tags is the first function's doc, not the file's.

To enforce JSDoc at commit time, declare the languages for [`clew guard`](../GUARD.md#javascript-and-typescript).

## Call edges

| Call | Edge |
|---|---|
| `f()` | `ast`, resolved by name |
| `this.m()`, `super.m()` | `ast_member`, qualified by the enclosing class (`Class.m`) |
| `obj.m()` | `ast_member`, with `obj` as the receiver |
| `new Foo()` | to `Foo.constructor`, when the class defines one |
| `arr.map(fn)`, `setTimeout(tick)` | `binding`: a function passed by name |

A member call whose receiver cannot be typed (`obj.m()`, `s.trim()`) is graded `fuzzy`, as in
C and Python: a function of that name exists, the specific one is unconfirmed. Reachability and
thread traversals do not follow fuzzy edges.

Inside a method, a bare `m()` is never treated as recursion: JavaScript has no implicit
`this`, so it names some other `m` (the same rule as Python methods).

## Limitations

- **No type inference.** Receivers are names, not types, so most `obj.m()` edges are fuzzy.
- **Imports are not followed.** A call to an imported function resolves by name across the
  repo, not through the `import` statement.
- **Threads, locks and shared keys** have no JavaScript model and stay empty.
- **Test files** follow the usual conventions (`*.test.*`, `*.spec.*`, `__tests__/`) for
  test-scope reporting.
