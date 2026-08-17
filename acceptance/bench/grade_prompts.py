## @brief Judging prompts + the anonymiser that keeps the judge blind to the arm.
## @version 2
"""Every string a judge ever sees is built here, so blindness is auditable in
one place.

`anonymise()` is the load-bearing piece. An answer file leaks its arm three
ways: the runner's `# Q1 — mcp — haiku — run 1` header, the mcp brief's
mandatory `## Index gaps` section heading, and any mention of the MCP tool
names. All three are scrubbed. What is *not* scrubbed is an answer's own prose
about how it found something ("the index does not resolve it") — removing that
would edit the evidence being judged. That residual leak is a stated limitation
of the quality axis, not a silent one.

THE `## Index gaps` HEADING IS NO LONGER ASKED FOR, and the scrub for it STAYS. Both briefs
now request the same `## Gaps` section, so the two arms' output contracts are byte-identical
and there is nothing to normalise on a new run — asymmetry in what an arm is TOLD is a
handicap built into the harness, and this was the last one outside the arm definitions
themselves. The pattern is kept because answers already collected use the old heading, and
re-grading a stored cell has to anonymise it as well as a fresh one. A scrub whose input has
stopped arriving costs one regex; deleting it silently un-blinds every historical answer.
"""

from __future__ import annotations

import re

_HEADER = re.compile(r"^#\s+Q\d+\s*[—–-].*$", re.MULTILINE)
_TOOL = re.compile(r"mcp__[A-Za-z0-9_-]+__([A-Za-z0-9_]+)")
_GAPS_HEADING = re.compile(
    r"^(#{1,6}\s*)(index gaps|db gaps|source gaps)\s*$", re.IGNORECASE | re.MULTILINE
)
_ARM_WORD = re.compile(r"\b(mcp arm|src arm|db arm|raw arm)\b", re.IGNORECASE)

## THE VERDICT SET, AND THE PROMPT IS RENDERED FROM IT. Previously the prompt listed its
## verdicts in prose while `grade_matrix` handed the extractor a separate inline tuple, with
## nothing tying the two — and a token offered to the judge but missing from the tuple parses
## as unreadable and becomes `JUDGE_ERROR`, which weighs exactly what a genuine MISS weighs.
## So a prompt/parser disagreement would have presented as the ANSWER being wrong rather than
## as the GRADER being broken.
##
## PARTIAL IS GONE (owner, 2026-08-13): "No partial grades, no half points, a mark is a mark."
## `questions-TEMPLATE.md` had said the same thing all along; the code disagreed with the
## written rule, weighting it 0.5 in one place and again via a separate hardcoded 0.5 in
## another, neither of them read by any test.
##
## Under atomic marks a half point is not a finer measurement — it is a refusal to decide,
## averaged into a headline. So the rule below is deliberately STRICT: an answer that gestures
## at the item without stating it is a MISS, and the prompt says so rather than leaving the
## judge to invent its own tie-break now that the middle option is absent.
MARK_VERDICTS: tuple[str, ...] = ("HIT", "MISS")

_VERDICT_RULES: dict[str, str] = {
    "HIT": (
        "the answer states the substance of the item. Different wording is fine, and a "
        "missing line number is fine if the mechanism and the location are named. FORMAT AND "
        "PLACEMENT ARE NOT GRADED: a fact stated in a table cell, a bullet, a heading, a code "
        "comment, a subordinate clause or in passing is STATED. Nor is emphasis — an item is "
        "not owed a sentence of its own, a prominent position, or a particular order. If you "
        "can quote the substance, it is a HIT."
    ),
    "MISS": (
        "the substance is absent. This INCLUDES an answer that gestures at the item, gets part "
        "of it, or names the thing without the specific mechanism the item requires — each item "
        "is ONE atomic fact, so it is either stated or it is not. There is no middle verdict and "
        "you must not invent one. Being torn about WHETHER THE FACT IS THERE resolves to MISS; "
        "being torn about how well it is PHRASED does not — that is not yours to grade."
    ),
}


## @brief Strip arm / model / run identity from an answer before judging.
## @param answer Raw answer markdown.
## @return Anonymised text.
## @version 1
def anonymise(answer: str) -> str:
    """@brief Remove the identifiers that would tell a judge which arm wrote this.
    @return Anonymised answer text.
    @version 1
    """
    text = _HEADER.sub("", answer)
    text = _TOOL.sub(r"a \1 lookup", text)
    text = _GAPS_HEADING.sub(r"\1Gaps", text)
    text = _ARM_WORD.sub("this approach", text)
    return text.strip()


## @brief Prompt asking the judge to settle ONE rubric mark.
## @param mark_text The frozen mark text.
## @param answer Anonymised answer.
## @return Prompt string.
## @version 3
def mark_prompt(mark_text: str, answer: str) -> str:
    """The judge is told it cannot read the codebase deliberately: its job is
    "does the answer demonstrate this item", not "is this item true".

    The verdict block is GENERATED from `MARK_VERDICTS`, so the set the judge is offered and
    the set the extractor accepts cannot drift apart.

    QUOTE COMES BEFORE VERDICT, AND THAT ORDER IS THE FIX. It used to be VERDICT then QUOTE, with
    the instruction to check the quote "in your head, not on the page" — so the judge committed to
    a verdict and only afterwards produced the evidence, with no retrieval step in between. That is
    exactly how a reply reads `VERDICT: MISS / QUOTE: NONE` against text sitting in the paragraph
    it was grading, which is what four independent forensic passes over one graded run found:
    12 of 39 misses were facts the answer states, several verbatim.

    THE SECOND HALF IS RHETORICAL GRADING, and it needed the rules changed rather than the order.
    Measured instances from the same run: a fact was failed FOR BEING IN A TABLE ROW; two marks
    were graded off ONE sentence with opposite verdicts; and twice the judge's own WHY conceded the
    fact and then ruled MISS on "framing". Under D2 a mark is one atomic FACT — arrangement,
    prominence and phrasing are not gradeable properties, and `_VERDICT_RULES` now says so on both
    sides rather than leaving "anything else" to be read as licence.

    @brief Build the per-mark judging prompt.
    @return Prompt string.
    @version 3
    """
    width = max(len(token) for token in MARK_VERDICTS)
    rules = "\n".join(f"{token:<{width}} — {_VERDICT_RULES[token]}" for token in MARK_VERDICTS)
    return f"""You are grading ONE checklist item from a frozen grading key against a candidate
answer about a software codebase. You have NO access to the codebase; judge only
whether the ANSWER demonstrates the item. Do not reward the answer for being good
in general — judge THIS item and nothing else.

CHECKLIST ITEM:
{mark_text}

CANDIDATE ANSWER:
<<<ANSWER
{answer}
ANSWER>>>

Verdicts:
{rules}

SEARCH THE ANSWER FIRST, THEN DECIDE — in that order. Scan the whole answer,
including its tables, bullets, headings and parenthetical asides, for the substance of
the item. Write the quote down BEFORE you settle the verdict. If you find the
substance, the verdict is HIT and you must not then talk yourself out of it on the
grounds of wording, prominence or arrangement. QUOTE: NONE and VERDICT: HIT is a
contradiction; so is quoting the item's substance and then answering MISS.

Reply with EXACTLY ONE of these blocks, as the LAST thing in your reply, substituting
your own values for the placeholders (never copy the placeholder text). Do not emit a
VERDICT line more than once, and do not show a verdict you then revise:
QUOTE: <short verbatim quote from the answer carrying the item's substance, or NONE>
VERDICT: <one of {", ".join(MARK_VERDICTS)}>
WHY: <one line>"""


## THE FALSITY PASS'S VERDICT SET, separate from `MARK_VERDICTS` because it answers a
## different question. `mark_prompt` asks "does the answer DEMONSTRATE this item" and tells the
## judge it has no access to the codebase — so it structurally cannot rule on whether a
## statement is TRUE, which is what D3's veto needs. Reusing it would have asked the judge the
## one question its own instructions forbid.
FALSITY_VERDICTS: tuple[str, ...] = ("CONTRADICTED", "CONSISTENT")


## @brief Prompt asking whether an answer contradicts the established ground truth.
## @param truths Ground-truth statements, each independently verified against source.
## @param answer Anonymised answer.
## @return Prompt string.
## @version 1
def falsity_prompt(truths: list[str], answer: str) -> str:
    """WHAT THIS DETECTS, AND WHAT IT DOES NOT — stated because the limit is the honest part.
    It detects an answer CONTRADICTING a fact we have established. It does not detect arbitrary
    falsehood, because nothing here knows the whole repository. So a clean CONSISTENT means
    "contradicts nothing we checked", never "everything it says is true", and the reply must be
    read that way.

    That bounded version is still the case that bit us. The index reported one first-party
    thread where two exist, its payload told the agent to quote that number as the repository's
    thread count, and the graded answer duly wrote "consistent with the index's count of exactly
    one first-party thread." A confident, well-formed, false sentence — which under the owner's
    rule 8 is the tool's fault, not the answer's, because the agent is instructed to trust the
    index absolutely.

    OMISSION IS NOT CONTRADICTION, and the prompt says so twice. Completeness is already scored
    by the marks; letting the veto also fire on incompleteness would double-count it and turn
    every low-scoring answer into a zeroed one.

    @brief Build the ground-truth contradiction prompt.
    @return Prompt string.
    @version 1
    """
    established = "\n".join(f"- {t}" for t in truths)
    return f"""You are checking ONE candidate answer about a software codebase against a list of
facts that have each been independently verified against that codebase's source.

Your ONLY question: does the answer ASSERT something that CONTRADICTS one of these facts?

ESTABLISHED FACTS:
{established}

CANDIDATE ANSWER:
<<<ANSWER
{answer}
ANSWER>>>

Rules, and the first one decides most cases:
- NOT MENTIONING a fact is NOT a contradiction. Silence is incompleteness, which is scored
  elsewhere. Only an assertion that cannot be true given a fact above counts.
- A contradiction is a specific, checkable clash: a different count of the same things, a
  claim that something does not exist when a fact says it does, a mechanism stated as X when
  a fact says Y.
- Vaguer or hedged wording that is consistent with a fact is CONSISTENT, not a contradiction.
- If you are unsure whether a statement clashes, answer CONSISTENT. This verdict zeroes the
  answer's whole score, so it must be earned by a clash you can point at.

Verdicts:
CONTRADICTED — the answer asserts something that cannot be true given a fact above.
CONSISTENT   — it contradicts none of them (whether or not it mentions them).

Reply with EXACTLY ONE of these blocks, as the LAST thing in your reply:
VERDICT: <one of {", ".join(FALSITY_VERDICTS)}>
QUOTE: <the verbatim sentence from the answer that clashes, or NONE>
WHY: <one line naming which established fact it clashes with>"""


## @brief Blind pairwise quality-comparison prompt.
## @param question The frozen question both answers address.
## @param answer_a Anonymised answer presented as A.
## @param answer_b Anonymised answer presented as B.
## @return Prompt string.
## @version 1
def pairwise_prompt(question: str, answer_a: str, answer_b: str) -> str:
    """Nothing in this prompt identifies where either answer came from; the
    A/B-to-arm mapping lives only in the caller's sidecar.

    @brief Build the blind pairwise judging prompt.
    @return Prompt string.
    @version 1
    """
    return f"""Two independent answers to the same question about a software codebase are below.
Compare them. You have NO access to the codebase, so judge on internal evidence:
specificity, self-consistency, and whether cited symbols and file:line references are
used in a way that actually supports the claim they are attached to.

QUESTION:
{question}

ANSWER A:
<<<A
{answer_a}
A>>>

ANSWER B:
<<<B
{answer_b}
B>>>

Judge each criterion independently:
- CORRECTNESS: internal consistency and plausibility of the mechanism described.
- CAUSAL_COMPLETENESS: does it follow the chain to a real terminus (a hardware write,
  bytes on a wire, a library call at the process boundary) rather than stopping at an
  intermediate state change?
- CITATION_INTEGRITY: are symbols and file:line citations specific, consistent, and
  actually attached to the claim they support (versus vague or decorative)?
- CLARITY: is the causal order easy to follow?

Length is not a merit. A shorter answer that is correct beats a longer one that pads.

Reply in EXACTLY this form and nothing else, substituting your own verdict for each
placeholder (never copy the placeholder text):
CORRECTNESS: <A, B or TIE>
CAUSAL_COMPLETENESS: <A, B or TIE>
CITATION_INTEGRITY: <A, B or TIE>
CLARITY: <A, B or TIE>
OVERALL: <A, B or TIE>
WHY: <one line>

Each value must be exactly A, B, or TIE — nothing else on those lines."""
