# SPDX-License-Identifier: MIT
"""Where a C function body really ends, read from the raw text when the parse cannot say.

gh#62. Inside preprocessor conditionals tree-sitter's error recovery produces `function_definition`
nodes that do not match the source: measured on mbedtls 068ff080, `ssl_parse_server_key_exchange`
spanned lines 2163-3688 against a real end of 2542 and swallowed three functions, and
`ssl_parse_server_hello` stopped at 1639 against 1665, leaving two `if` blocks recovered as
"functions". A blanket filter does not work: 472 of 2,983 bodied definitions on that tree carry
`has_error` and most of their ranges are right.

THE BODY'S OWN BRACES SETTLE IT. From the body's opening `{`, the matching `}` is found by
counting braces in the text, skipping comments, string and character literals and directive
lines. Only the FIRST branch of each `#if`/`#ifdef`/`#ifndef` group is counted — the `#elif` and
`#else` branches are alternatives to it, and counting both is exactly how a duplicated
`if (...) {` opener unbalances the count. A heuristic, and bounded: a body whose braces never
balance returns None, and the parse's own extent stands.

@brief Brace-matched end of a C body, preprocessor-aware.
@version 1
"""

from __future__ import annotations

## Directives that open a conditional group, and those that start an alternative branch of one.
_OPEN = ("if", "ifdef", "ifndef")
_ALTERNATIVE = ("elif", "elifdef", "elifndef", "else")


## @brief The 1-based line of the `}` closing the body whose `{` is at `start`, or None.
## @param src The file's bytes.
## @param start Byte offset of the body's opening `{`.
## @return The closing line, or None when the braces never balance.
## @version 1
## @utility
def body_end_line(src: bytes, start: int) -> int | None:
    """@brief Brace-match a body. @return Line or None."""
    scan = _Scanner(src, start)
    return scan.run()


## @brief One pass over the text from a body's opening brace.
## @version 1
## @dg_internal
class _Scanner:
    """A cursor and the two counters the match needs: brace depth, and how many conditional
    groups deep the cursor is inside a SKIPPED branch.

    @brief Brace scanner.
    @version 1
    """

    ## @brief Start at a body's opening brace.
    ## @version 1
    ## @dg_internal
    def __init__(self, src: bytes, start: int) -> None:
        self.src = src
        self.pos = start
        self.depth = 0
        ## Conditional nesting, one entry per open group: True once its first branch has ended,
        ## so the rest of the group is skipped.
        self.groups: list[bool] = []

    ## @brief Scan until the opening brace's match.
    ## @return The closing line, or None.
    ## @version 1
    ## @dg_internal
    def run(self) -> int | None:
        """@brief Scan. @return Line or None."""
        src = self.src
        while self.pos < len(src):
            if src[self.pos : self.pos + 1] == b"#" and self._at_line_start() and self._directive():
                continue
            if any(self.groups):
                self.pos += 1
                continue
            if self._skip_literal_or_comment():
                continue
            ch = src[self.pos : self.pos + 1]
            if ch == b"{":
                self.depth += 1
            elif ch == b"}":
                self.depth -= 1
                if self.depth == 0:
                    return src.count(b"\n", 0, self.pos) + 1
            self.pos += 1
        return None

    ## @brief Whether the cursor is at the first non-blank character of a line.
    ## @return True when only spaces or tabs precede it on its line.
    ## @version 1
    ## @dg_internal
    def _at_line_start(self) -> bool:
        """@brief Line start. @return True or False."""
        line_start = self.src.rfind(b"\n", 0, self.pos) + 1
        return self.src[line_start : self.pos].strip(b" \t") == b""

    ## @brief Consume a preprocessor directive line, updating the conditional groups.
    ## @return True when a directive was consumed.
    ## @version 1
    ## @dg_internal
    def _directive(self) -> bool:
        """@brief Consume a directive. @return True when one was."""
        if self.src[self.pos : self.pos + 1] != b"#":
            return False
        end = self._line_end()
        words = self.src[self.pos + 1 : end].split()
        word = words[0].decode("ascii", "replace") if words else ""
        if word in _OPEN:
            self.groups.append(False)
        elif word in _ALTERNATIVE and self.groups:
            self.groups[-1] = True
        elif word == "endif" and self.groups:
            self.groups.pop()
        self.pos = end
        return True

    ## @brief The offset just past a directive line, following backslash continuations.
    ## @return Byte offset.
    ## @version 1
    ## @dg_internal
    def _line_end(self) -> int:
        """@brief Directive end. @return Offset."""
        pos = self.pos
        while True:
            nl = self.src.find(b"\n", pos)
            if nl < 0:
                return len(self.src)
            if self.src[nl - 1 : nl] != b"\\":
                return nl + 1
            pos = nl + 1

    ## @brief Skip a comment or a string/character literal at the cursor.
    ## @return True when one was skipped.
    ## @version 1
    ## @dg_internal
    def _skip_literal_or_comment(self) -> bool:
        """@brief Skip a literal or comment. @return True when skipped."""
        src, pos = self.src, self.pos
        two = src[pos : pos + 2]
        if two == b"//":
            nl = src.find(b"\n", pos)
            self.pos = len(src) if nl < 0 else nl
            return True
        if two == b"/*":
            close = src.find(b"*/", pos + 2)
            self.pos = len(src) if close < 0 else close + 2
            return True
        quote = src[pos : pos + 1]
        if quote in (b'"', b"'"):
            self.pos = _literal_end(src, pos, quote)
            return True
        return False


## @brief The offset just past a string or character literal.
## @param src The file's bytes.
## @param pos Offset of the opening quote.
## @param quote The quote byte.
## @return Offset past the closing quote, or the line end for an unterminated literal.
## @version 1
## @dg_internal
def _literal_end(src: bytes, pos: int, quote: bytes) -> int:
    """@brief Literal end. @return Offset."""
    i = pos + 1
    while i < len(src):
        ch = src[i : i + 1]
        if ch == b"\\":
            i += 2
            continue
        if ch == quote or ch == b"\n":
            return i + 1
        i += 1
    return i
