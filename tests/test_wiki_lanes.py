"""Per-flow lanes (UX review A-2, owner Q/A 2026-11-22)."""

from clew.wiki.flow import Flow, Lane, Step


def _st(callee: str, site: str, file: str, a: str = "blk", b: str = "blk") -> Step:
    """@brief A step: called from `site`, defined in `file`, drawn on block lanes a → b."""
    return Step("m", "m", callee, callee, a, b, file, 1, 1, site_file=site)


def _flow(steps: list[Step]) -> Flow:
    """@brief A flow on one block lane."""
    return Flow("m", "m", 2, "blocks", (Lane("blk", "blk"),), tuple(steps))


def test_a_flow_drawn_on_one_block_is_redrawn_on_its_files() -> None:
    """Measured on clew's 36 master flows: block lanes left 85-95% of arrows as self-calls; file
    lanes gave 2-15x more cross-lane calls. Each flow takes whichever of the two shows more calls
    between lanes, the drawing only (`clew wiki flow` keeps its lanes).

    @brief Files win when they show more.
    """
    from clew.wiki.lanes import per_flow_lanes

    flow = _flow([_st("a", "m.py", "x.py"), _st("b", "x.py", "y.py"), _st("c", "y.py", "y.py")])
    drawn = per_flow_lanes(flow)
    assert [ln.id for ln in drawn.lanes] == ["m.py", "x.py", "y.py"]
    assert [(s.from_lane, s.to_lane) for s in drawn.steps] == [
        ("m.py", "x.py"),
        ("x.py", "y.py"),
        ("y.py", "y.py"),
    ]
    assert drawn.lane_strategy == "files"


def test_block_lanes_stay_when_files_show_no_more() -> None:
    """@brief Ties keep the blocks (coarser, the map's words)."""
    from clew.wiki.lanes import per_flow_lanes

    flow = _flow([_st("a", "m.py", "m.py", "A", "B"), _st("b", "m.py", "m.py", "B", "B")])
    flow = Flow("m", "m", 2, "blocks", (Lane("A", "A"), Lane("B", "B")), flow.steps)
    assert per_flow_lanes(flow) is flow


def test_at_most_seven_file_lanes_the_quietest_shared() -> None:
    """@brief Six busiest files keep a lane; the rest share "other files"."""
    from clew.wiki.lanes import OTHER, per_flow_lanes

    files = [f"f{i}.py" for i in range(9)]
    steps = [_st(f"c{i}", files[i], files[i + 1]) for i in range(8)]
    steps += [_st("again", "f0.py", "f1.py")] * 3
    drawn = per_flow_lanes(_flow(steps))
    assert len(drawn.lanes) == 7 and drawn.lanes[-1].id == OTHER
    assert {"f0.py", "f1.py"} <= {ln.id for ln in drawn.lanes}
