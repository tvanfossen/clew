# SPDX-License-Identifier: MIT
"""How a spawned thread ends: joined, detached, a daemon, or unknown — and the line that says so.

2.1, the index pair (owner Q/A 2026-11-24). FOUND in the 2.0.0 grid (entropic Q4, −25.4 points):
the graded fact is that ONE thread is detached (`std::thread(...).detach()`,
external_bridge.cpp:1222) while every other is joined, and the threads layer recorded where each
thread was spawned but nothing about how it ends, so agents read every spawning file.

READ FROM THE SPAWNING FILE'S OWN SYNTAX, NEVER GUESSED:
- chained on the spawn call: `std::thread(...).detach()` / `.join()`;
- through a handle: `x = std::thread(...)` (or `t = threading.Thread(...)`), then `x.join()` /
  `x.detach()` somewhere in the SAME FILE, matched by the handle's last name, so `ct->thread` and
  `(*it)->thread` are one handle. Same-file and by name: a handle joined from another file is
  `unknown`, which is what the file alone can say;
- `std::jthread` joins itself on destruction;
- `pthread_create(&tid, ...)` with `pthread_join(tid, ...)` / `pthread_detach(tid)`;
- Python `daemon=True` on the constructor.
A handle with both a detach and a join reads as `detached` (the one a reader must know about).
Nothing found is `unknown`, with no line.

@brief Thread lifecycle from the spawning file's syntax.
@version 1
"""

from __future__ import annotations

import re
from typing import Any

from .vocabulary import LIFECYCLE_DAEMON, LIFECYCLE_DETACHED, LIFECYCLE_JOINED, LIFECYCLE_UNKNOWN

## The method or function name that ends a handle, by grammar, and the state it means.
_ENDS = {
    "join": LIFECYCLE_JOINED,
    "detach": LIFECYCLE_DETACHED,
    "pthread_join": LIFECYCLE_JOINED,
    "pthread_detach": LIFECYCLE_DETACHED,
}
## The separators a handle expression is split on to find its last name.
_SPLIT = re.compile(r"->|\.|::")
## Kinds that create no thread to end (a handler registration, a timer callback, the main
## context): their lifecycle is NULL, the question not applying, never "unknown".
NO_LIFECYCLE = frozenset({"isr", "timer", "main"})
## A plain name: a handle that is a LOCAL when it is declared at the spawn.
_PLAIN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


## @brief A handle expression's last name: `ct->thread` → `thread`, `&tid` → `tid`.
## @param text The expression as written.
## @return The name, or "".
## @version 1
## @utility
def handle_name(text: str) -> str:
    """@brief Handle name. @return Name."""
    return _SPLIT.split(text.strip())[-1].strip("*&()[] \t")


## @brief A node's text.
## @param node A tree-sitter node, or None.
## @param src The file's bytes.
## @return The text, or "".
## @version 1
## @utility
def _text(node: Any, src: bytes) -> str:
    """@brief Text. @return Str."""
    return "" if node is None else src[node.start_byte : node.end_byte].decode("utf-8", "replace")


## @brief The handle a call ends, and how: `x.join()`, `pthread_detach(tid)`.
## @param call A call node.
## @param src The file's bytes.
## @return (handle name, state, line), or None when the call ends no handle.
## v2 (2.1, found measuring entropic): the line is the END's own (`.detach` at 1222), not where
## the call expression starts (a lambda spawn at 1158).
## @version 2
## @utility
def _ended(call: Any, src: bytes) -> tuple[str, str, int] | None:
    """C++ `field_expression` (`argument`, `field`) and Python `attribute` (`object`, `attribute`)
    are the two member-call shapes; a bare `pthread_*` call names its handle as the first argument.

    @brief Ended handle.
    @return Triple or None.
    """
    fn = call.child_by_field_name("function")
    if fn is None:
        return None
    if fn.type in ("field_expression", "attribute"):
        member = fn.child_by_field_name("field") or fn.child_by_field_name("attribute")
        obj = fn.child_by_field_name("argument") or fn.child_by_field_name("object")
        state = _ENDS.get(_text(member, src))
        found = state and member is not None and obj is not None
        return (handle_name(_text(obj, src)), state, member.start_point[0] + 1) if found else None
    args = call.child_by_field_name("arguments")
    first = next((c for c in (args.named_children if args else ()) if c.type != "comment"), None)
    state = _ENDS.get(_text(fn, src)) if fn.type == "identifier" else None
    found = state and first is not None
    return (handle_name(_text(first, src)), state, call.start_point[0] + 1) if found else None


## @brief Every handle the file ends, by name: {name: [(state, line), ...]}, in file order.
## @version 1
class Lifecycles:
    """ONE WALK PER FILE, built lazily by the spawn walk the first time a spawn matches.

    @brief A file's join/detach sites.
    @version 1
    """

    ## @brief Collect the file's join and detach calls.
    ## @param root The file's root node.
    ## @param src The file's bytes.
    ## @return None.
    ## @version 1
    ## @utility
    def __init__(self, root: Any, src: bytes) -> None:
        """@brief Init. @return None."""
        self.src = src
        ## {handle: [(state, line, byte offset)]}; the offset places an end inside a function.
        self.ends: dict[str, list[tuple[str, int, int]]] = {}
        stack = [root]
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            if node.type not in ("call_expression", "call"):
                continue
            ended = _ended(node, src)
            if ended is not None and ended[0]:
                self.ends.setdefault(ended[0], []).append((ended[1], ended[2], node.start_byte))
        for sites in self.ends.values():
            sites.sort(key=lambda s: s[1])

    ## @brief How the thread a spawn call creates ends.
    ## @param spawn The spawn call node.
    ## @param callee The spawn callee as written (`std::jthread`, `pthread_create`).
    ## @param target The spawn's assignment target, "" when none.
    ## @param kind The spawn's `threads.kind`.
    ## @return (state, line); line is None for `unknown`; both None for a kind with no lifecycle.
    ## @version 1
    ## @req REQ-DDB-SCHEMA-001
    def of(self, spawn: Any, callee: str, target: str, kind: str) -> tuple[str | None, int | None]:
        """Order: what the spawn expression itself says (chained, jthread, daemon), then the
        handle's ends — inside the spawning function for a local, anywhere in the file otherwise.

        @brief Lifecycle of one spawn.
        @return Pair.
        """
        if kind in NO_LIFECYCLE:
            return None, None
        found = self._inline(spawn, callee) or self._by_handle(*self._handle(spawn, callee, target))
        return found or (LIFECYCLE_UNKNOWN, None)

    ## @brief What the spawn expression itself settles: chained end, `std::jthread`, `daemon=True`.
    ## @param spawn The spawn call node.
    ## @param callee The callee as written.
    ## @return (state, line), or None.
    ## @version 1
    ## @utility
    def _inline(self, spawn: Any, callee: str) -> tuple[str, int | None] | None:
        """@brief Inline lifecycle. @return Pair or None."""
        line = spawn.start_point[0] + 1
        parent = spawn.parent
        outer = parent.parent if parent is not None else None
        if outer is not None and outer.type in ("call_expression", "call"):
            ended = _ended(outer, self.src)
            if ended is not None and parent.type in ("field_expression", "attribute"):
                return ended[1], ended[2]
        if callee.endswith("jthread"):
            return LIFECYCLE_JOINED, line
        return (LIFECYCLE_DAEMON, line) if _daemon_keyword(spawn, self.src) else None

    ## @brief The handle a spawn's thread is held by.
    ## @param spawn The spawn call node.
    ## @param callee The callee as written.
    ## @param target The C/C++ assignment target, "" when none.
    ## @return (the handle's last name or "", the spawning function's node when it is a local).
    ## @version 1
    ## @utility
    def _handle(self, spawn: Any, callee: str, target: str) -> tuple[str, Any]:
        """`pthread_create`'s handle is its first argument; a Python spawn's is its assignment's
        left side; a C++ one's is the target the spawn walk already computed.

        A LOCAL is a plain name the spawn's own syntax declares — a Python assignment (Python has
        no implicit members), a C++ `std::thread x = ...`, a `pthread_create(&tid, ...)` — and its
        end must be in the same function. FOUND MEASURING clew's own tree: a `child` killed in one
        test was credited with another test's `child.join()`. `worker_ = std::thread(...)` may be
        a member, so it stays file-wide.

        @brief Handle and scope.
        @return Pair.
        """
        local = False
        if callee == "pthread_create":
            args = spawn.child_by_field_name("arguments")
            first = next(iter(args.named_children), None) if args is not None else None
            target = _text(first, self.src).lstrip("&").strip()
            local = True
        elif not target and spawn.parent is not None and spawn.parent.type == "assignment":
            target = _text(spawn.parent.child_by_field_name("left"), self.src)
            local = True
        else:
            local = _declared_at(spawn)
        plain = bool(_PLAIN.fullmatch(target.strip()))
        return handle_name(target), _function_of(spawn) if local and plain else None

    ## @brief The handle's same-file end: the first detach, else the first join.
    ## @param handle The handle's last name.
    ## @param scope The spawning function's node for a local, else None (file-wide).
    ## @return (state, line), or None.
    ## @version 1
    ## @utility
    def _by_handle(self, handle: str, scope: Any) -> tuple[str, int | None] | None:
        """@brief By handle. @return Pair or None."""
        sites = [
            s
            for s in (self.ends.get(handle, []) if handle else [])
            if scope is None or scope.start_byte <= s[2] < scope.end_byte
        ]
        chosen = next((s for s in sites if s[0] == LIFECYCLE_DETACHED), None) or next(
            iter(sites), None
        )
        return (chosen[0], chosen[1]) if chosen else None


## @brief The function definition a node sits in.
## @param node A node.
## @return The `function_definition` node, or None at file scope.
## @version 1
## @utility
def _function_of(node: Any) -> Any:
    """@brief Enclosing function. @return Node or None."""
    while node is not None and node.type != "function_definition":
        node = node.parent
    return node


## @brief Whether a C/C++ spawn's handle is declared at the spawn (`std::thread x = ...`).
## @param spawn The spawn call node.
## @return True when an `init_declarator` holds it.
## @version 1
## @utility
def _declared_at(spawn: Any) -> bool:
    """@brief Declared here. @return Bool."""
    node = spawn.parent
    for _ in range(6):
        if node is None or node.type == "function_definition":
            return False
        if node.type == "init_declarator":
            return True
        node = node.parent
    return False


## @brief Whether a Python constructor call passes `daemon=True`.
## @param spawn The call node.
## @param src The file's bytes.
## @return True when it does.
## @version 1
## @utility
def _daemon_keyword(spawn: Any, src: bytes) -> bool:
    """@brief Daemon keyword. @return Bool."""
    args = spawn.child_by_field_name("arguments")
    return any(
        c.type == "keyword_argument"
        and _text(c.child_by_field_name("name"), src) == "daemon"
        and _text(c.child_by_field_name("value"), src) == "True"
        for c in (args.named_children if args is not None else ())
    )
