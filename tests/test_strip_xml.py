# SPDX-License-Identifier: MIT
"""Served description text keeps code text doxygen stored verbatim (owner Q/A 2026-11-20).

`query._common.strip_xml` feeds dossier, search and corpus replies. Its regex tag-strip removed
anything between `<` and `>`, so `(n_tokens < 2) … ENTROPIC_ERROR_EVAL_FAILED (llama_decode
error)` served as "(n_tokens", and `std::atomic<bool>` as "std::atomic". The wiki was fixed in
314e4696; the owner chose to fix served text in 2.0.0 too, with the same rule.

@brief Tests strip_xml on verbatim code text.
@version 1
"""

from __future__ import annotations

from clew.query._common import strip_xml


def test_a_less_than_and_a_template_argument_survive() -> None:
    """@brief Code text stays; doxygen markup goes."""
    assert strip_xml("<para>Fails (n_tokens < 2) on a std::atomic<bool>.</para>") == (
        "Fails (n_tokens < 2) on a std::atomic<bool>."
    )
    ## Stored entities are served as stored, as test_jsts pins for `Map&lt;string`.
    assert strip_xml("<para>a &amp; b</para>") == "a &amp; b"


def test_markup_is_still_removed() -> None:
    """@brief The ordinary case is unchanged: tags become spaces, runs collapse."""
    assert (
        strip_xml('<para>See <ref refid="x">f</ref>.</para><para>Next.</para>') == "See f . Next."
    )
    assert strip_xml(None) == ""
