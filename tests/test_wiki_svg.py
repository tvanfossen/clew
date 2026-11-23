def test_a_flow_svg_draws_scenario_bands() -> None:
    """X-1 (owner 2026-11-22): the scenario lives IN the sequence diagram — a band labelled with its
    Gherkin line from the step its anchor names to the next band, keyword marked.

    @brief Scenario bands.
    """
    from clew.wiki.flow import Flow, Lane, Step
    from clew.wiki.svg import flow_svg

    lanes = (Lane("a", "a"), Lane("b", "b"))
    steps = tuple(
        Step(
            caller="m",
            caller_qualified="m",
            callee=c,
            callee_qualified=c,
            from_lane="a",
            to_lane="b",
            file="b.py",
            line=i + 1,
            depth=1,
        )
        for i, c in enumerate(("x", "y", "z"))
    )
    flow = Flow(
        entry="m", entry_qualified="m", depth=1, lane_strategy="files", lanes=lanes, steps=steps
    )
    svg = flow_svg(flow, segments={0: "When it starts", 2: "Then it ends"})
    assert svg.count('class="segband') == 2
    assert (
        '<tspan class="kw">When</tspan> it starts' in svg
        and '<tspan class="kw">Then</tspan> it ends' in svg
    )


def test_band_labels_sit_on_top_with_a_backing() -> None:
    """Owner screenshot 2026-11-22: band labels ran under frame tags and step labels. The labels are
    drawn LAST, each on a backing pill; the band's tint stays behind the lanes.

    @brief Labels after everything else.
    """
    from clew.wiki.flow import Flow, Lane, Step
    from clew.wiki.svg import flow_svg

    steps = (
        Step(
            caller="m",
            caller_qualified="m",
            callee="x",
            callee_qualified="x",
            from_lane="a",
            to_lane="b",
            file="b.py",
            line=1,
            depth=1,
        ),
    )
    flow = Flow(
        entry="m",
        entry_qualified="m",
        depth=1,
        lane_strategy="files",
        lanes=(Lane("a", "a"), Lane("b", "b")),
        steps=steps,
    )
    svg = flow_svg(flow, segments={0: "When it starts"})
    assert svg.rindex('class="seglabel') > svg.rindex('data-step="0"') and 'class="lbg"' in svg


def _st(callee: str, a: str, b: str, depth: int, line: int = 1, caller: str = "m"):  # noqa: ANN202
    """@brief A step for the fold tests."""
    from clew.wiki.flow import Step

    return Step(caller, caller, callee, callee, a, b, f"{b}.py", line, depth)


def _flow(steps):  # noqa: ANN001, ANN202
    """@brief A two-lane flow."""
    from clew.wiki.flow import Flow, Lane

    return Flow("m", "m", 3, "files", (Lane("a", "a"), Lane("b", "b")), tuple(steps))


def test_a_run_of_calls_inside_one_lane_draws_as_one_row() -> None:
    """UX review A-2 (owner Q/A 2026-11-22): with block lanes 85-95% of clew's arrows were
    self-calls (dossier: 218 of 243), each a row. A run of two or more consecutive calls that stay
    inside one lane — same mark, never shallower than its first — draws as ONE row, "first +N
    more", standing for all of them (the player and step table still see every step).

    @brief Internal runs fold.
    """
    from clew.wiki.svg import flow_svg

    steps = [
        _st("enter", "a", "b", 1),
        _st("p", "b", "b", 2, 2, "enter"),
        _st("q", "b", "b", 3, 3, "p"),
        _st("r", "b", "b", 2, 4, "enter"),
        _st("back", "b", "a", 2, 5, "enter"),
    ]
    svg = flow_svg(_flow(steps))
    assert svg.count("data-step=") == 3
    assert 'data-steps="1 2 3"' in svg and ">p +2 more<" in svg
    assert "loop ×" not in svg


def test_a_fold_never_spans_marks_or_climbs_out_of_its_subtree() -> None:
    """@brief A lit step does not fold with a dim one; a shallower call starts a new row."""
    from clew.wiki.svg import flow_svg

    steps = [
        _st("enter", "a", "b", 1),
        _st("p", "b", "b", 3, 2),
        _st("q", "b", "b", 2, 3),
        _st("r", "b", "b", 2, 4),
    ]
    svg = flow_svg(_flow(steps), marks={3: "ex"})
    assert svg.count("data-step=") == 4


def test_a_step_badge_number_is_at_least_eleven_pixels() -> None:
    """UX review rule (owner Q/A 2026-11-22): no diagram text under 11 px. Measured at 1:1 on the
    dossier flow (ee3c934f): the 299 step numbers were the only text under it, at 10 px.

    @brief Badge numbers 11 px, in a circle that holds them.
    """
    from clew.wiki.svg import _STYLE, flow_svg

    assert ".seq .num{fill:#fff;font-size:11px" in _STYLE
    svg = flow_svg(_flow([_st("enter", "a", "b", 1)]))
    assert 'class="badge"' in svg and 'r="9"' in svg


def test_a_tall_diagram_repeats_its_lane_names() -> None:
    """Found in the browser (group A): with the diagram in its own scrolling box, the lane heads
    scrolled out of sight and the reader lost which column was which. A lane's name repeats as a
    faint tag down its lifeline, every `_REPEAT_HEADS` px, beneath the steps (zoom and pan move it
    with the drawing, since it is part of it).

    @brief Repeated lane names.
    """
    from clew.wiki.svg import _REPEAT_HEADS, flow_svg

    steps = [_st(f"c{i}", "a" if i % 2 else "b", "b" if i % 2 else "a", 1, i) for i in range(60)]
    svg = flow_svg(_flow(steps))
    height = int(svg.split('height="', 1)[1].split('"', 1)[0])
    assert height > 3 * _REPEAT_HEADS
    assert svg.count('class="head-r"') == 2 * ((height - 60) // _REPEAT_HEADS)
    assert svg.index('class="head-r"') < svg.index("data-step=")
