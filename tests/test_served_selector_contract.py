# SPDX-License-Identifier: MIT
"""The served instruction told the model to pass a value the code rejects.

**A MODEL THAT OBEYED THE DOCUMENTATION GOT NOTHING BACK.** `dossier`'s `qualified` parameter
selects one identity when a name matched several. The description the model receives said:

    "The exact signature from a previous reply's `candidates`, to pick one overload."

The accessor requires `candidates[i].qualified` — the bare qualified name — and compares by exact
string equality, failing closed (`clew/query/_common.py:331-342`). A `signature` is doxygen's
`definition` column, which carries the return type: `"Any pkg.harvest.Harvester.harvest"` against
a required `"pkg.harvest.Harvester.harvest"`. Those can never be equal, so following the
instruction produced `found: false` — and the model's next move is to retry the bare name it was
already failing on.

**THIS IS NOT HYPOTHETICAL.** A cell traced by hand on the 1.1.0 grid called `dossier('execute')`
four times for a symbol the index holds as `ServerManager::execute`, wasting 5 of 16 calls.

**WHY THE EXISTING SUITE DID NOT CATCH IT, WHICH IS THE REAL DEFECT.**
`tests/test_disambiguation.py` pins thoroughly that the CODE accepts `qualified`, and its fixture
deliberately uses a `definition` that differs from the qualified name, so a code regression would
fail instantly. `tests/test_mcp_server.py` asserts only that a description EXISTS and that the
substring `"qualified"` appears in the guidance — which passes on the wrong wording. Nothing
asserted that **the instruction and the accepted input agree**. Two correct halves, no test across
the seam.

That seam is what this file tests. It checks a PROPERTY of every served string — never the wording
of one sentence, which a legitimate rewrite would break for no reason.

@brief Served disambiguation guidance must name the field the code accepts.
@version 1
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

from clew.mcp_server import tools_query
from clew.query._common import matching_identity, qualified_name_of

## The shape doxygen really emits: a `definition` carrying a return type, and the qualified name
## that is its tail. Borrowed from `tests/test_disambiguation.py`'s fixture so the two agree.
_DEFINITION = "Any pkg.harvest.Harvester.harvest"
_QUALIFIED = "pkg.harvest.Harvester.harvest"
_NAME = "harvest"

_SOURCE = Path(tools_query.__file__)


##
# @brief Passing a signature where a qualified name is required must select nothing.
# @return None.
# @version 1
def test_a_signature_cannot_select_an_identity() -> None:
    """THE PREMISE OF EVERY OTHER TEST HERE, asserted rather than assumed. If this starts failing
    because the accessor grew a signature fallback, then the served wording was never a defect and
    the rest of this file is measuring nothing — delete it rather than keeping it green.

    @brief A signature selects nothing.
    @return None.
    @version 1
    """
    cands = [(1, _DEFINITION)]

    assert qualified_name_of(_NAME, _DEFINITION) == _QUALIFIED
    assert matching_identity(_NAME, cands, _QUALIFIED), "the qualified name must select the row"
    assert not matching_identity(_NAME, cands, _DEFINITION), (
        "a signature now selects an identity, so the premise of this file no longer holds"
    )


##
# @brief The served `qualified` parameter description must name the field the code accepts.
# @return None.
# @version 1
def test_the_served_parameter_description_names_qualified_not_signature() -> None:
    """THE PYDANTIC `Field` DESCRIPTION IS WHAT REACHES THE MODEL, in the one channel a client
    cannot truncate — `tests/test_mcp_server.py:150-162` already pins that every parameter's
    description appears in the generated schema. This is the exact string an agent reads at the
    moment it decides what to pass.

    Read from the function's `Annotated` metadata rather than from a built schema, so no live
    server is needed and a schema assembled elsewhere cannot satisfy it.

    Both halves are asserted, because "names `qualified`" alone passed the entire time the wording
    was wrong: the parameter is itself called `qualified`.

    @brief The parameter description is correct.
    @return None.
    @version 1
    """
    ## `inspect.get_annotations`, NOT `typing.get_type_hints`. The latter applies PEP 484's
    ## implicit-Optional handling to every parameter defaulting to None, which DROPS the
    ## `Annotated` metadata for exactly `kind`, `qualified`, `sub_index` and `target` — so the
    ## first version of this test silently saw no description for the one parameter it exists to
    ## check, and the presence assertion below is what caught it.
    hints = inspect.get_annotations(tools_query.QueryTools.dossier, eval_str=True)
    served = {
        name: str(getattr(meta, "description", "") or "")
        for name, hint in hints.items()
        for meta in getattr(hint, "__metadata__", ())
        if getattr(meta, "description", None)
    }

    assert "qualified" in served, (
        f"dossier serves no description for `qualified`; found {sorted(served)}. An absent "
        f"description is not a pass — the model would be told nothing at all."
    )
    text = served["qualified"]
    assert "qualified" in text, f"the selector's description does not name it: {text!r}"
    assert not _directs_to_a_signature(text), (
        f"the served description still tells the model to pass a signature, which the accessor "
        f"refuses by exact match — a model that obeys it gets found:false. Text: {text!r}"
    )


##
# @brief No served `how_to_narrow` may steer the model to a signature or a file selector.
# @return None.
# @version 1
def test_no_runtime_guidance_steers_to_a_signature() -> None:
    """THESE STRINGS ARE READ AT THE WORST POSSIBLE MOMENT. `how_to_narrow` is the advice carried
    inside a reply that has just told the model its name was ambiguous, so it is what the model
    acts on immediately. Two of them said "the signature you mean" and "lists the signatures".

    One also advertised "Narrow by file", which **no accessor supports** — `matching_identity`'s
    docstring records that a `file` selector was considered and REJECTED. Advertising a parameter
    that does not exist is the same defect in a second place.

    SCANNED BY AST OVER EVERY `how_to_narrow` IN THE MODULE, not by calling the builders: one of
    them needs a live index to reach its string, and a test that skipped it would leave the
    worst-placed guidance uncovered. A property over all sites also covers the next one somebody
    adds, which a per-site test would not.

    @brief Runtime guidance is correct.
    @return None.
    @version 1
    """
    served = _how_to_narrow_strings()

    assert len(served) >= 4, (
        f"only {len(served)} how_to_narrow string(s) found in {_SOURCE.name}; the scan is not "
        f"reaching them and would pass vacuously"
    )

    offences = []
    for line, text in served:
        lowered = text.lower()
        if "qualified" not in lowered:
            ## Not every `how_to_narrow` is about the selector — some advise narrowing a corpus
            ## or a sub-index. Those are out of this test's scope and are skipped, not failed.
            continue
        if _directs_to_a_signature(text):
            offences.append(f"{_SOURCE.name}:{line} steers to a signature: {text!r}")
        if "narrow by file" in lowered:
            offences.append(f"{_SOURCE.name}:{line} advertises a file selector: {text!r}")

    assert not offences, "served disambiguation guidance is wrong:\n  " + "\n  ".join(offences)


##
# @brief Every `how_to_narrow` literal in the served module, with its line.
# @return Pairs of line number and the literal text it carries.
# @version 1
# @dg_internal
def _how_to_narrow_strings() -> list[tuple[int, str]]:
    """Flattens f-strings and implicit concatenation down to their CONSTANT parts, which is where
    the guidance wording lives; an interpolated count is not guidance. A value that is a plain
    name — the string passed into `_limited_block` from elsewhere — contributes nothing and is
    skipped, since the literal it refers to is scanned at its own definition site.

    @brief Served how_to_narrow literals.
    @return Line and text pairs.
    @version 1
    """
    tree = ast.parse(_SOURCE.read_text("utf-8"))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "how_to_narrow":
                text = _literal_text(value)
                if text:
                    out.append((getattr(value, "lineno", node.lineno), text))
    return out


##
# @brief Collect the constant string parts of an expression node.
# @param node The expression.
# @return The concatenated constant text.
# @version 1
# @dg_internal
def _literal_text(node: ast.AST) -> str:
    """@brief Constant text within an expression.
    @param node The expression.
    @return Concatenated constants.
    @version 1
    """
    parts = [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]
    return " ".join(parts)


##
# @brief Whether served text DIRECTS the model to pass a signature.
# @param text The served string.
# @return True when it names a signature other than to warn against one.
# @version 1
# @dg_internal
def _directs_to_a_signature(text: str) -> bool:
    """**BANNING THE WORD OUTRIGHT WAS THE FIRST ATTEMPT AND IT WAS WRONG.** The best wording for
    this guidance warns against the trap — "the qualified name, NOT the signature" — so a test
    that forbade the word would have forced strictly worse text and then been worked around. The
    property that actually matters is whether the text DIRECTS the model to a signature, not
    whether it mentions one.

    So an occurrence is permitted when a negator sits close in front of it, and that is checked by
    proximity rather than by a list of phrases: a phrase list only ever catches the wordings
    already shipped, and the next one is written by someone who has not read this file.

    @brief Does the text direct the model to a signature.
    @param text The served string.
    @return True when it does.
    @version 1
    """
    lowered = text.lower()
    negators = ("not ", "never ", "rather than ", "n't ", "instead of ")
    for match in re.finditer(r"signature", lowered):
        window = lowered[max(0, match.start() - 40) : match.start()]
        if not any(word in window for word in negators):
            return True
    return False
