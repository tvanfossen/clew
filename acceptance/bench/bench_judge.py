## @brief Headless `claude -p` LLM-judge primitives (strict verdicts, no fabrication).
## @version 1
"""Ask a fresh, tool-less `claude -p` process to settle one judgement.

Two rules the rest of the grader depends on:

1. **The judge gets no tools** (`--allowedTools ""`). It reads only the text it
   is handed, so a verdict can never be laundered from a file the judge went and
   read; the evidence in the sidecar is the evidence it saw.
2. **Unparseable output is `judge_error`, never a score.** Every parser here
   returns `None` on a missing/ambiguous verdict token and the caller records
   the raw text. A grader that silently scored 0 on a malformed reply would
   quietly punish whichever arm happened to trip the judge.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT = 180


## @brief One judge invocation's raw outcome.
## @version 1
@dataclass
class JudgeReply:
    """@brief Raw judge text plus any transport-level error.
    @version 1
    """

    text: str = ""
    error: str = ""


## @brief Invoke the judge CLI and return its raw stdout or a transport error.
## @param argv Full argument vector.
## @param timeout Seconds before the call is abandoned.
## @return (stdout, error) — exactly one of the two is non-empty.
## @version 1
## @dg_internal
def _invoke(argv: list[str], timeout: int) -> tuple[str, str]:
    """Transport only. Kept separate from parsing so a timeout and a malformed
    reply stay distinguishable in the record — they cost a reviewer very
    different things, and lumping them together is how 102 marks the judge never
    ruled on once got counted as failures.

    @brief Run the judge subprocess.
    @return (stdout, error).
    @version 1
    """
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return "", f"judge timeout after {timeout}s"
    if not proc.stdout.strip():
        return "", f"judge produced no stdout (rc={proc.returncode})"
    return proc.stdout, ""


## @brief Turn the judge CLI's JSON envelope into a JudgeReply.
## @param stdout Raw stdout from a successful invocation.
## @return JudgeReply carrying the text, or an error string.
## @version 1
## @dg_internal
def _parse(stdout: str) -> JudgeReply:
    """@brief Decode the judge's JSON result envelope.
    @return JudgeReply.
    @version 1
    """
    try:
        payload = json.loads(stdout)
    except ValueError:
        return JudgeReply(error="judge stdout was not JSON")
    if payload.get("is_error"):
        return JudgeReply(error=f"judge reported error: {payload.get('result', '')}")
    return JudgeReply(text=(payload.get("result") or "").strip())


## @brief Run one headless, tool-less judging prompt.
## @param prompt The full judging prompt.
## @param model Model alias for the judge.
## @param timeout Seconds before the call is abandoned.
## @return JudgeReply with the model's text, or an error string.
## @version 2
def ask(prompt: str, model: str = DEFAULT_MODEL, timeout: int = DEFAULT_TIMEOUT) -> JudgeReply:
    """Mirrors the runner's invocation shape exactly, minus tools.

    @brief Invoke `claude -p` for a single judgement.
    @return JudgeReply.
    @version 2
    """
    argv = [
        "claude",
        "-p",
        prompt,
        "--model",
        model,
        "--output-format",
        "json",
        "--allowedTools",
        "",
    ]
    stdout, error = _invoke(argv, timeout)
    return JudgeReply(error=error) if error else _parse(stdout)


## @brief One verdict extraction, with whether it had to disambiguate.
## @version 1
@dataclass(frozen=True)
class VerdictExtraction:
    """@brief Extracted token plus the evidence for how it was chosen.
    @version 1
    """

    token: str | None = None
    tokens: tuple[str, ...] = ()
    disambiguated: bool = False


## @brief Pull a strict verdict token out of a judge reply.
## @param text Judge reply text.
## @param label Field label, e.g. "VERDICT".
## @param allowed Permitted tokens.
## @return VerdictExtraction; token is None only when NO valid token is present.
## @version 2
def extract_verdict(text: str, label: str, allowed: tuple[str, ...]) -> VerdictExtraction:
    """Requires `LABEL: TOKEN` on its own line — a token merely *mentioned* in
    prose still does not count. What changed in v2 is what happens when the reply
    contains SEVERAL such lines that disagree.

    v1 returned None for that case, on the reasoning that disagreement is
    ambiguity and ambiguity must not be scored. Measured against the first full
    grid, that reasoning was wrong about the actual failure: **all 14 unparsed
    replies were a judge SELF-CORRECTING.** Every one had the same shape —

        VERDICT: HIT
        QUOTE: "..."
        WHY: Wait — that quote is not in the candidate answer ...
        VERDICT: MISS
        QUOTE: NONE
        WHY: The answer never addresses ...

    i.e. the judge started to award the mark, went looking for the supporting
    quote, found it absent, and corrected itself. The reply is not ambiguous; it
    is reasoning followed by a conclusion, and the conclusion is LAST.

    Refusing those was not a neutral act. A `judge_error` is deliberately never
    scored 0 and is excluded from the evaluated denominator, so refusing them
    silently DELETED near-zero marks — 13 of the 14 resolve to MISS — from
    whichever arm produced more of them (10 against 4). Fail-closed on the parse
    became fail-OPEN on the score.

    So: the LAST valid token wins, and `disambiguated` records that it had to be
    chosen, so a disambiguated grade is never mistaken for a clean one. `None` is
    still returned when there is NO valid token at all — that case is a genuine
    format failure with nothing to conclude from.

    @brief Extract the judge's final verdict token.
    @return VerdictExtraction.
    @version 2
    """
    pattern = re.compile(
        rf"^\s*{label}\s*[:\-]\s*\**([A-Za-z_]+)\**\s*$", re.IGNORECASE | re.MULTILINE
    )
    ## Ordered, not a set: which token came LAST is the whole signal.
    found = tuple(m.group(1).upper() for m in pattern.finditer(text))
    valid = tuple(t for t in found if t in set(allowed))
    if not valid:
        return VerdictExtraction(token=None, tokens=found)
    return VerdictExtraction(
        token=valid[-1],
        tokens=valid,
        disambiguated=len(set(valid)) > 1,
    )


## @brief Pull a strict verdict token out of a judge reply.
## @param text Judge reply text.
## @param label Field label, e.g. "VERDICT".
## @param allowed Permitted tokens.
## @return The token, or None when no valid token is present.
## @version 2
def verdict_token(text: str, label: str, allowed: tuple[str, ...]) -> str | None:
    """Thin wrapper over `extract_verdict` for callers that do not record the
    disambiguation. Prefer `extract_verdict` anywhere the result is written to a
    sidecar a human will read.

    @brief Extract one verdict token.
    @return Token or None.
    @version 2
    """
    return extract_verdict(text, label, allowed).token


## @brief Pull a free-text field out of a judge reply.
## @param text Judge reply text.
## @param label Field label.
## @return The field's single-line value, or "".
## @version 1
def field(text: str, label: str) -> str:
    """@brief Extract a one-line labelled field.
    @return Field value or empty string.
    @version 1
    """
    pattern = re.compile(rf"^\s*{label}\s*[:\-]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    found = pattern.search(text)
    return found.group(1).strip() if found else ""


## @brief One majority-voted verdict across N judge samples.
## @version 1
@dataclass
class Vote:
    """@brief Majority verdict + how strong the agreement was.
    @version 1
    """

    verdict: str | None = None
    agreement: float = 0.0
    tally: tuple = ()
    samples: int = 0
    errors: int = 0


## @brief Run one judging prompt N times and majority-vote the verdict token.
## @param prompt The full judging prompt.
## @param label Verdict field label (e.g. "VERDICT").
## @param allowed Permitted tokens.
## @param n Number of independent judge samples (odd avoids ties).
## @param model Judge model alias.
## @return Vote with the majority verdict, agreement ratio, and per-token tally.
## @version 1
def vote(
    prompt: str,
    label: str,
    allowed: tuple[str, ...],
    n: int = 3,
    model: str = DEFAULT_MODEL,
) -> Vote:
    """Judge nondeterminism is real — a single mark's verdict was observed to
    move across reruns. For any verdict that actually matters, sample the judge
    `n` times and take the majority, reporting how divided it was so a shaky
    verdict is visible rather than laundered into a clean number. A sample whose
    output is unparseable counts as an error, not a vote (never fabricated).

    AGREEMENT IS OVER SAMPLES REQUESTED, NOT SAMPLES SURVIVING, and the difference was a
    live CRITICAL defect. Dividing by the number of successful votes made one vote out of
    three unanimous: a single CONTRADICTED beside two errored samples returned
    `agreement=1.0`, which is exactly `grade_matrix.VETO_AGREEMENT`, so the D3 veto FIRED and
    zeroed a whole question on one sample. The veto therefore got EASIER to trip the flakier
    the judge became — and judge flakiness here is caused by exhausting session capacity,
    which is the constraint that actually binds a sweep. `falsity_check`'s own docstring
    already promised "ERRORS DO NOT VETO"; that held only when EVERY sample errored, which is
    the case nobody worries about.

    An errored sample is not a concurring vote. Under this denominator 1-of-3 reads 0.33 and
    cannot reach unanimity, while a genuine 3-of-3 still reads 1.0.

    @brief Majority-voted judge verdict across n samples.
    @return Vote.
    @version 2
    """
    from collections import Counter

    counts: Counter = Counter()
    errors = 0
    requested = max(1, n)
    for _ in range(requested):
        reply = ask(prompt, model=model)
        if reply.error:
            errors += 1
            continue
        tok = verdict_token(reply.text, label, allowed)
        if tok is None:
            errors += 1
            continue
        counts[tok] += 1
    if not counts:
        return Vote(verdict=None, agreement=0.0, tally=(), samples=n, errors=errors)
    top, top_n = counts.most_common(1)[0]
    return Vote(
        verdict=top,
        ## `requested`, NEVER `sum(counts.values())` — see the docstring. The survivor
        ## denominator turned one vote of three into unanimity and armed the veto on it.
        agreement=top_n / requested,
        tally=tuple(sorted(counts.items())),
        samples=n,
        errors=errors,
    )
