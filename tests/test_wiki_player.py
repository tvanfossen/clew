# SPDX-License-Identifier: MIT
"""The flow player paces to reading speed, presents in a modal, and never scrolls the diagram away.

OWNER REVIEW 2026-11-22 (W-3, W-4, W-7):

- "add a flow speed … and allow me to slow it down … average human reading speed, find a whitepaper
  and cite it". Each step dwells for its words at 238 words per minute, the mean silent-reading rate
  of English adults for non-fiction (Brysbaert 2019, J. Memory and Language 109:104047), with a
  floor; a speed control scales it. Learner-paced segments are Mayer & Moreno's (2003, Educational
  Psychologist 38(1):43–52) segmenting principle.
- "the dossier flow is so long … that it hides the sequence diagram as it walks the table rows below
  it". Sync lit each row with `scrollIntoView`, moving the PAGE. Rows are lit, never scrolled to.
- "a modal showing only the current action, high-level details, and the sequence diagram". A
  present control opens a dialog holding the diagram, the current step and the controls.

@brief Tests the flow player.
@version 1
"""

from __future__ import annotations

from clew.wiki import flowpage


def test_the_player_paces_to_the_cited_reading_rate() -> None:
    """@brief The script carries 238 wpm and its citation, and a step's dwell has a floor."""
    script = flowpage._SCRIPT
    assert "WPM=238" in script and "Brysbaert" in flowpage.__doc__ + script
    assert "MIN_MS=" in script


def test_the_player_has_a_speed_control_and_a_present_mode() -> None:
    """@brief A speed range input and a present control; the dialog holds diagram and current step."""
    html = flowpage._controls()
    assert 'type="range"' in html and "data-flow-speed" in html
    assert 'data-flow-control="present"' in html
    ## The page's ONE modal presents it (test_one_modal_component_serves_every_page).
    assert "register('flow-present'" in flowpage._SCRIPT and "flow-now" in flowpage._SCRIPT


def test_sync_lights_rows_without_scrolling_the_page() -> None:
    """@brief No scrollIntoView on the step table: the diagram stays where the reader left it."""
    assert "scrollIntoView" not in flowpage._SCRIPT
