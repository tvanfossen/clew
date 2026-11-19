# SPDX-License-Identifier: MIT
"""A test's checks, pinned by syntax tree to the function each one observes (round 5, P5.5).

OWNER (round 5): checks are pinned by syntax tree. Each assertion in a test body is one of:

| kind | when |
|---|---|
| direct | a call to a candidate is inside the assertion: `assert save(1) == 1` |
| via variable | the assertion reads a name assigned from a candidate's call earlier in the body |
| not attributed | neither: said, not guessed |

The candidates are the functions the test calls, from the index. When a check contains calls to
several, the OUTERMOST candidate is the one it observes: `assert clean(save(1))` checks the value
`clean` returned (`_outermost`). Python is read with `ast`; C and C++ with tree-sitter through `clew.tsnode`, over
the common assertion macros. Any other language pins nothing, and the page lists its checks
unpinned, as before.

@brief Pin a test's assertions to the functions they observe.
@version 1
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass
from pathlib import PurePosixPath

DIRECT = "direct"
VIA_VARIABLE = "via variable"
NOT_ATTRIBUTED = "not attributed"

_C_SUFFIXES = {".c": "c", ".h": "c"}
_CPP_SUFFIXES = {".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp"}
## The assertion macros of the common C/C++ frameworks: Catch2 / doctest, GoogleTest, Unity, assert.
_C_ASSERT = re.compile(r"^(REQUIRE\w*|CHECK\w*|EXPECT_\w+|ASSERT_\w+|TEST_ASSERT\w*|assert)$")
## Python's assertion calls besides the `assert` statement: unittest's methods, pytest helpers.
_PY_ASSERT_CALL = re.compile(r"^(assert\w*|fail\w*)$")


## @brief One check and what it observes.
## @version 1
@dataclass(frozen=True)
class Pin:
    """@brief The statement, its kind, the function it observes, and the variable it read."""

    statement: str
    kind: str
    target: str | None = None
    variable: str | None = None


## @brief Pin each assertion in a test body to the candidate function it observes.
## @param lines The test definition's source lines.
## @param rel Its repository-relative file (the language is read from the suffix).
## @param candidates The names of the functions the test calls.
## @return One Pin per assertion, in body order; [] for a language without a parser.
## @version 1
## @req REQ-DDB-WIKI-043
def pin_checks(lines: list[str], rel: str, candidates: set[str]) -> list[Pin]:
    """@brief Dispatch by language. @return Pins."""
    suffix = PurePosixPath(rel).suffix
    if suffix == ".py":
        return _python(lines, candidates)
    lang = _C_SUFFIXES.get(suffix) or _CPP_SUFFIXES.get(suffix)
    return _c_family(lines, lang, candidates) if lang else []


## @brief Pin a Python test body.
## @param lines The definition's lines.
## @param candidates Candidate names.
## @return Pins.
## @version 1
## @utility
def _python(lines: list[str], candidates: set[str]) -> list[Pin]:
    """A BODY THAT WILL NOT PARSE pins nothing rather than raising: the page still lists its
    checks, read the old way.

    @brief `ast` walk.
    @return Pins.
    """
    source = textwrap.dedent("\n".join(lines))
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    assigned: dict[str, str] = {}
    pins: list[Pin] = []
    for node in _statements(tree):
        if isinstance(node, ast.Assign):
            called = _outermost(_py_calls(node.value), candidates)
            for name in (t.id for t in node.targets if isinstance(t, ast.Name)):
                if called:
                    assigned[name] = called
        elif _is_py_assertion(node):
            text = " ".join((ast.get_source_segment(source, node) or "").split())
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            pins.append(_pin(text, _py_calls(node), names, assigned, candidates))
    return pins


## @brief The statements of the (first) function in a parsed body, in order, nested blocks included.
## @param tree The parsed module.
## @return Statements.
## @version 1
## @utility
def _statements(tree: ast.AST) -> list[ast.stmt]:
    """@brief Statements in source order. @return Nodes."""
    out = [
        n for n in ast.walk(tree) if isinstance(n, ast.stmt) and not isinstance(n, ast.FunctionDef)
    ]
    return sorted(out, key=lambda n: (n.lineno, n.col_offset))


## @brief Whether a statement is an assertion: `assert`, or a call such as `self.assertEqual(...)`.
## @param node A statement.
## @return True for an assertion.
## @version 1
## @utility
def _is_py_assertion(node: ast.stmt) -> bool:
    """@brief Assertion statement or call. @return Flag."""
    if isinstance(node, ast.Assert):
        return True
    call = node.value if isinstance(node, ast.Expr) else None
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    return bool(_PY_ASSERT_CALL.match(name))


## @brief The called names in a Python node, outermost first.
## @param node The node.
## @return Names.
## @version 1
## @utility
def _py_calls(node: ast.AST) -> list[str]:
    """@brief Call names in walk order (outer before inner). @return Names."""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            func = n.func
            out.append(func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", ""))
    return out


## @brief Pin a C or C++ test body through tree-sitter.
## @param lines The definition's lines.
## @param lang `c` or `cpp`.
## @param candidates Candidate names.
## @return Pins.
## @version 1
## @utility
def _c_family(lines: list[str], lang: str, candidates: set[str]) -> list[Pin]:
    """A DECLARATION OR ASSIGNMENT from a candidate's call binds its variable; an assertion
    macro's call is then pinned exactly as in Python.

    @brief tree-sitter walk.
    @return Pins.
    """
    from ..tsnode import Parser

    root = Parser(lang).parse("\n".join(lines).encode()).root_node
    assigned: dict[str, str] = {}
    pins: list[Pin] = []
    for node in _walk(root):
        bound = _c_binding(node, candidates)
        if bound:
            assigned[bound[0]] = bound[1]
        elif node.type == "call_expression" and _C_ASSERT.match(_callee(node)):
            names = {_text(n) for n in _walk(node) if n.type == "identifier"}
            calls = [_callee(n) for n in _walk(node) if n.type == "call_expression"][1:]
            pins.append(_pin(" ".join(_text(node).split()), calls, names, assigned, candidates))
    return pins


## @brief A (variable, candidate) a declaration or assignment binds, or None.
## @param node A tree-sitter node.
## @param candidates Candidate names.
## @return The binding, or None.
## @version 1
## @utility
def _c_binding(node, candidates: set[str]) -> tuple[str, str] | None:  # noqa: ANN001
    """@brief `auto r = save(1);` and `r = save(1);`. @return Binding."""
    if node.type not in ("init_declarator", "assignment_expression"):
        return None
    left = node.child_by_field_name("declarator" if node.type == "init_declarator" else "left")
    right = node.child_by_field_name("value" if node.type == "init_declarator" else "right")
    if left is None or right is None or left.type != "identifier":
        return None
    calls = [_callee(n) for n in _walk(right) if n.type == "call_expression"]
    called = _outermost(calls, candidates)
    return (_text(left), called) if called else None


## @brief Every node under one, in source order.
## @param node The root.
## @return Nodes, pre-order.
## @version 1
## @utility
def _walk(node) -> list:  # noqa: ANN001
    """@brief Pre-order walk. @return Nodes."""
    out, stack = [], [node]
    while stack:
        current = stack.pop()
        out.append(current)
        stack.extend(reversed(current.children))
    return out


## @brief The called function's name of a call expression.
## @param node A `call_expression`.
## @return Its name, or "".
## @version 1
## @utility
def _callee(node) -> str:  # noqa: ANN001
    """@brief Last identifier of the function field (`ns::f`, `obj.f`, `f`). @return Name."""
    func = node.child_by_field_name("function")
    ids = [n for n in _walk(func) if n.type in ("identifier", "field_identifier")] if func else []
    return _text(ids[-1]) if ids else ""


## @brief A node's source text.
## @param node A tree-sitter node.
## @return Text.
## @version 1
## @utility
def _text(node) -> str:  # noqa: ANN001
    """@brief Decode. @return Text."""
    return node.text.decode("utf-8", errors="replace") if node is not None and node.text else ""


## @brief The first candidate among calls, outermost first.
## @param calls Called names, outermost first.
## @param candidates Candidate names.
## @return The name, or None.
## @version 1
## @utility
def _outermost(calls: list[str], candidates: set[str]) -> str | None:
    """THE VALUE CHECKED is the outermost candidate's: `assert clean(save(1))` checks what
    `clean` returned.

    @brief First candidate.
    @return Name or None.
    """
    return next((c for c in calls if c in candidates), None)


## @brief The Pin for one assertion.
## @param text The assertion's text.
## @param calls Calls inside it, outermost first.
## @param names Identifiers it reads.
## @param assigned Variable → the candidate that produced it.
## @param candidates Candidate names.
## @return The Pin.
## @version 1
## @utility
def _pin(text: str, calls: list[str], names: set[str], assigned: dict, candidates: set[str]) -> Pin:
    """@brief Direct, else via a variable, else not attributed. @return Pin."""
    target = _outermost(calls, candidates)
    if target:
        return Pin(text, DIRECT, target)
    var = next((n for n in sorted(names) if n in assigned), None)
    return Pin(text, VIA_VARIABLE, assigned[var], var) if var else Pin(text, NOT_ATTRIBUTED)
