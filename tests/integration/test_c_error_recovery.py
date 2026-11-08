# SPDX-License-Identifier: MIT
"""Error-recovered C definitions end where their braces close, and a keyword is never a function.

gh#62, on the pinned mbedtls tree (068ff080), whose own files are the reproduction — a small
synthetic file does not trigger tree-sitter's context-dependent recovery:

* `ssl_parse_server_key_exchange` was recorded as lines 2163-3688; it ends at 2542, and the three
  functions after it inside that range had no rows.
* `ssl_parse_server_hello` was cut at 1639; it ends at 1665, and two `if` blocks inside it were
  recovered as functions named `if` — ten such rows across five files.

@brief Real-tree tests for C error-recovery extents.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import lang_parsing_substrate as lps
import pytest

from clew.ast_symbols import harvest_function_definitions

pytestmark = pytest.mark.integration

_FILES = (
    "library/ssl_tls12_client.c",
    "library/ssl_msg.c",
    "programs/ssl/ssl_client2.c",
    "programs/ssl/ssl_server2.c",
    "programs/test/udp_proxy.c",
)
_KEYWORDS = {"if", "while", "for", "switch", "return", "sizeof", "else", "do", "case"}


## @brief The harvested definitions of one pinned file, by name.
## @param root The checkout.
## @param rel Repo-relative path.
## @return name -> [(start, end), ...].
## @version 1
def _spans(root: Path, rel: str) -> dict[str, list[tuple[int, int]]]:
    """@brief Harvest one file. @return Spans by name."""
    src = (root / rel).read_bytes()
    out: dict[str, list[tuple[int, int]]] = {}
    for fn in harvest_function_definitions(lps.parse_tree("c", src), src):
        out.setdefault(fn.name, []).append((fn.start, fn.end))
    return out


## @brief No recovered definition is named after a C keyword.
## @param mbedtls_checkout The pinned checkout.
## @return None.
## @version 1
def test_no_keyword_is_recovered_as_a_function(mbedtls_checkout: Path) -> None:
    """@brief Zero `if` functions in the five files that had ten.
    @return None.
    @version 1
    """
    found = {rel: sorted(set(_spans(mbedtls_checkout, rel)) & _KEYWORDS) for rel in _FILES}
    assert not any(found.values()), found


## @brief An overrunning or truncated definition ends where its body's braces close.
## @param mbedtls_checkout The pinned checkout.
## @return None.
## @version 1
def test_recovered_definitions_end_where_their_braces_close(mbedtls_checkout: Path) -> None:
    """@brief The two issue functions have their real extents; the swallowed three exist.
    @return None.
    @version 1
    """
    spans = _spans(mbedtls_checkout, "library/ssl_tls12_client.c")
    assert spans["ssl_parse_server_key_exchange"] == [(2163, 2542)], spans
    assert spans["ssl_parse_server_hello"] == [(1182, 1665)], spans
    for name in (
        "ssl_parse_certificate_request",
        "ssl_parse_server_hello_done",
        "ssl_write_client_key_exchange",
    ):
        assert name in spans, sorted(spans)
