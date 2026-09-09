# SPDX-License-Identifier: MIT
"""gh#37 — refresh and status replies carried unbounded build detail and overflowed.

MEASURED on a repository vendoring nine submodules: two `index(action='refresh')` replies in
one validation session exceeded the client's tool-result limit and were written to disk
instead of returned — 253,867 and 100,199 characters. An incremental refresh reply for a build
that changed nine files was ~100 KB.

WHAT FILLED THEM. Two things, neither of which a reader acts on:

  * `status.scope.excludes` carried the full resolved exclude list — ~390 entries, dominated
    by `deps/functional/b12-slam/deps/boost/libs/*/.github` and `.drone` paths — and the same
    list appeared again under `operator_excludes`;
  * `output` carried one `WARNING file_docs: could not read <header>, skipping` line per
    unresolved system include, ~95 of them, all the same shape.

THE SERVER'S OWN INSTRUCTIONS PROMISE 2,048 CHARACTERS PER SERVED STRING and note that a
client discards the rest in silence. These replies were two orders of magnitude past it, on
the two calls an operator makes most.

BOUNDED, NOT TRUNCATED IN SILENCE. Every bound here discloses what it dropped and where the
full text still is: the buildlog holds every line, is written incrementally, and is named in
the reply already. A cap that says nothing would be the client's silent discard reimplemented
one layer up.

THE REPEATED LINES ARE COLLAPSED RATHER THAN CUT, keeping the first verbatim. A reader who
needs to know that system headers went unresolved learns it from one line plus a count; a
reader who needs the ninety-five names has the buildlog. Cutting the middle of the stream
instead would risk dropping the one warning that names a real defect in the declaration.

@brief Tests for the bounds on refresh/status reply payloads.
@version 1
"""

from __future__ import annotations


def test_repeated_warnings_collapse_to_one_line_and_a_count() -> None:
    """THE REPORTED SHAPE. Ninety-five lines differing only in the header name are one fact,
    and a reply that spends ninety-five lines on it has spent them instead of on the stage
    costs and the coverage block a reader came for.

    @brief Same-shape warning lines collapse, keeping the first verbatim.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _bounded_output

    lines = [f"WARNING file_docs: could not read sys{i}.h, skipping" for i in range(95)]
    out = _bounded_output("\n".join(["INFO stage resolve: 96 ms", *lines, "INFO build complete"]))

    assert "INFO stage resolve: 96 ms" in out, "the stage costs are what a reader acts on"
    assert "INFO build complete" in out, "the tail must survive collapsing the middle"
    assert "sys0.h" in out, "the first of a collapsed group stays verbatim"
    assert "sys50.h" not in out, "the ninety-fifth namesake is buildlog material"
    assert "94" in out, "the count of collapsed lines must be disclosed"
    assert out.count("could not read") == 1, f"one line for the group, got:\n{out}"


def test_a_lone_warning_is_never_collapsed() -> None:
    """A GROUP OF ONE IS NOT A GROUP. Collapsing a single warning would replace a specific,
    actionable line with a count of one — strictly worse than leaving it, and the case where
    the header name is most likely to matter.

    @brief A single occurrence passes through verbatim.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _bounded_output

    text = "WARNING file_docs: could not read only.h, skipping\nINFO done"
    assert _bounded_output(text) == text


def test_distinct_warnings_are_not_merged_with_each_other() -> None:
    """THE RISK THIS RULE CARRIES, pinned. Grouping by shape must not fold two DIFFERENT
    diagnostics into one — a reader told "3 similar lines" when one of them named a broken
    declaration and another named an unreadable header has been actively misled.

    @brief Warnings of different shapes each survive.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _bounded_output

    out = _bounded_output(
        "\n".join(
            [
                "WARNING index_scope: roots: is required but absent",
                "WARNING file_docs: could not read a.h, skipping",
                "WARNING doxygen: INPUT names a path that does not exist",
            ]
        )
    )
    assert "roots: is required" in out
    assert "could not read a.h" in out
    assert "INPUT names a path" in out


def test_an_output_with_no_repetition_is_returned_unchanged() -> None:
    """THE CONTROL. Most builds emit a short, varied stream, and this must be a no-op for them
    — a bound that rewrites every reply is a bound nobody can reason about.

    @brief Varied short output is untouched.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _bounded_output

    text = "INFO resolve: 96 ms\nINFO doxygen: 3695 ms\nINFO coverage: 812/913 files\n"
    assert _bounded_output(text) == text


def test_a_huge_output_is_capped_whatever_its_shape() -> None:
    """THE BACKSTOP, because collapsing is content-dependent and the overflow must not be.
    253,867 characters reached a client that discards past its limit in silence; a bound that
    only works on the shapes seen so far is not a bound.

    @brief Output beyond the cap is trimmed with the omission disclosed.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _OUTPUT_CAP, _bounded_output

    text = "\n".join(f"INFO unique line {i} with padding {'x' * 60}" for i in range(4000))
    out = _bounded_output(text)

    assert len(out) <= _OUTPUT_CAP * 2, f"{len(out)} characters is not a bound"
    assert "buildlog" in out, "say where the full stream is"
    assert "INFO unique line 0" in out, "the head carries the scope explanation"
    assert "INFO unique line 3999" in out, (
        "the TAIL carries the build summary — `test_the_build_runs_in_process_and_keeps_stdout_"
        "clean` asserts `memberdef` reaches the caller, and it is the last thing emitted"
    )


def test_the_status_scope_block_does_not_carry_a_full_exclude_list() -> None:
    """~390 EXCLUDE ENTRIES IN A STATUS REPLY, twice — once under `excludes` and again under
    `operator_excludes`. The count is the fact a reader can act on; the entries are what the
    buildlog is for.

    @brief A long exclude string is replaced by its count.
    @return None.
    @version 1
    """
    from clew.mcp_server.state import _bounded_scope_meta

    entries = ",".join(f"deps/boost/libs/l{i}/.github" for i in range(390))
    bounded = _bounded_scope_meta({"source": "whole-repo", "excludes": entries})

    assert "390" in str(bounded.get("excludes_count", "")), bounded
    assert len(str(bounded.get("excludes", ""))) < 2048, "the served string cap is 2,048"
    assert bounded["source"] == "whole-repo", "the fields a reader acts on are untouched"


def test_a_short_operator_exclude_is_reported_verbatim() -> None:
    """THE CONTROL THAT KEEPS `operator_excludes` USEFUL. It is what the OPERATOR stated, so it
    is normally a word or two and is the field that tells them their own decision was recorded
    and replayed. Capping must not touch it at that size.

    @brief A short exclude string passes through unchanged.
    @return None.
    @version 1
    """
    from clew.mcp_server.state import _bounded_scope_meta

    bounded = _bounded_scope_meta({"source": "whole-repo", "operator_excludes": "evidence"})
    assert bounded["operator_excludes"] == "evidence"
    assert "operator_excludes_count" not in bounded, "a short value needs no count beside it"
