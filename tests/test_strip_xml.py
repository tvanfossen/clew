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
    ## SPEC CHANGED (owner Q/A 2026-11-23, 2.0.1): entities are DECODED after the elements go,
    ## superseding "served as stored" — see the test below.
    assert strip_xml("<para>a &amp; b</para>") == "a & b"


def test_one_character_has_one_spelling_in_a_reply() -> None:
    """FOUND BY ENTROPIC against the installed 2.0.0 (2026-11-23): doxygen stores the same
    character two ways — verbatim in some descriptions, as an entity in others (inside
    <computeroutput>) — so one reply could say `std::atomic&lt;bool&gt;` beside `n_tokens < 2`.
    Entities are decoded after doxygen's elements are removed, so a reply reads as the source.

    @brief Entities decoded after the strip.
    """
    stored = (
        "<para>Holds a <computeroutput>std::atomic&lt;bool&gt;</computeroutput> flag; "
        "n_tokens < 2 &amp; done.</para>"
    )
    assert strip_xml(stored) == "Holds a std::atomic<bool> flag; n_tokens < 2 & done."
    ## An entity spelling markup is text once decoded: it is never stripped as an element.
    assert strip_xml("<para>write &lt;para&gt; literally</para>") == "write <para> literally"


def test_markup_is_still_removed() -> None:
    """@brief The ordinary case is unchanged: tags become spaces, runs collapse."""
    assert (
        strip_xml('<para>See <ref refid="x">f</ref>.</para><para>Next.</para>') == "See f . Next."
    )
    assert strip_xml(None) == ""
