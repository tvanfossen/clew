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
