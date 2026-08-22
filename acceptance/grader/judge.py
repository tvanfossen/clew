# SPDX-License-Identifier: MIT
"""Every string a judge ever sees is built here, so blindness is auditable in one place.

WHAT THE JUDGE IS SHOWN, and the list is short on purpose:

  * for a verdict call — ONE mark's text and the anonymised answer;
  * for an extraction call — one `extract` instruction and the anonymised answer.

WHAT IT IS NEVER SHOWN: the arm, the model, the transcript, the target, the other marks, a
mark's `evidence`, or the correct set. Rubric-blindness is the load-bearing one — a judge shown
the expected answer scores by similarity to it rather than by whether the answer states the
thing.

The judge also has no codebase access. Its question is "does the answer demonstrate this item",
never "is this item true". Whether the item is true was settled when the mark was authored.

EXTRACTION IS A DIFFERENT JOB FROM EVALUATION, which is why set marks use their own call.
"What does this text name?" has no threshold in it; "is this close enough to count?" does, and
that threshold is where a judge wobbles. Set scoring keeps the judge on the side without one and
leaves recall and precision to arithmetic.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections import Counter
from dataclasses import dataclass

VERDICTS: tuple[str, ...] = ("HIT", "MISS")

## Attempts per judge call and the pause between them. Three rides out a busy window without
## turning a genuinely broken invocation into a long hang.
ASK_ATTEMPTS = 3
ASK_BACKOFF_SECONDS = 4
DEFAULT_TIMEOUT = 180

_HEADER = re.compile(r"^#\s+Q\d+\s*[—–-].*$", re.MULTILINE)
_TOOL = re.compile(r"mcp__[A-Za-z0-9_-]+__([A-Za-z0-9_]+)")
_GAPS = re.compile(
    r"^(#{1,6}\s*)(index gaps|db gaps|source gaps)\s*$", re.IGNORECASE | re.MULTILINE
)
_ARM = re.compile(r"\b(mcp arm|src arm|db arm|raw arm|index arm|baseline arm)\b", re.IGNORECASE)

_RULES = {
    "HIT": (
        "the answer states the substance of the item. Different wording is fine, and a missing "
        "line number is fine if the mechanism and the location are named. FORMAT AND PLACEMENT "
        "ARE NOT GRADED: a fact stated in a table cell, a bullet, a heading, a code comment, a "
        "subordinate clause or in passing is STATED. Nor is emphasis — an item is not owed a "
        "sentence of its own or a prominent position. If you can quote the substance, it is a HIT."
    ),
    "MISS": (
        "the substance is absent. This INCLUDES an answer that gestures at the item, gets part of "
        "it, or names the thing without the specific mechanism the item requires — each item is "
        "ONE atomic fact, so it is either stated or it is not. There is no middle verdict and you "
        "must not invent one. Being torn about WHETHER THE FACT IS THERE resolves to MISS; being "
        "torn about how well it is PHRASED does not — that is not yours to grade."
    ),
}


## @brief One judge invocation's outcome.
## @version 1
@dataclass(frozen=True)
class Reply:
    """@brief Raw judge text plus any transport-level error.
    @version 1
    """

    text: str = ""
    error: str = ""


## @brief A voted verdict across independent samples.
## @version 2
@dataclass(frozen=True)
class Vote:
    """@brief Majority verdict, its agreement ratio, and the errors that did not vote.
    @version 2
    """

    verdict: str | None
    agreement: float
    tally: tuple
    samples: int
    errors: int
    ## Why each failed attempt failed, in order. Empty on a clean vote.
    reasons: tuple = ()


## @brief Strip arm, model and run identity from an answer before judging.
## @param answer Raw answer markdown.
## @return Anonymised text.
## @version 1
def anonymise(answer: str) -> str:
    """An answer leaks its arm three ways: the runner's header line, a tool-named call, and the
    words "index arm" / "baseline arm" in its own prose.

    WHAT IS NOT SCRUBBED is an answer's own prose about HOW it found something ("the index does
    not resolve that"). Removing it would edit the evidence being judged. That residual leak is
    a stated limitation, not a silent one.

    @brief Remove arm identity.
    @return Anonymised answer.
    @version 1
    """
    text = _HEADER.sub("", answer)
    text = _TOOL.sub(r"a \1 lookup", text)
    text = _GAPS.sub(r"\1Gaps", text)
    return _ARM.sub("this approach", text).strip()


## @brief Invoke the judge CLI once.
## @param prompt Full prompt text.
## @param model Dated model id — never an alias.
## @param timeout Seconds before the call is abandoned.
## @return Reply.
## @version 2
def ask(prompt: str, model: str, timeout: int = DEFAULT_TIMEOUT) -> Reply:
    """Tool-less and fresh every call, which is what makes repeated calls a variance measurement
    rather than a conversation.

    A timeout and a malformed reply stay distinguishable in the record: they cost a reviewer
    very different things, and lumping them together is how marks the judge never ruled on once
    got counted as failures.

    @brief One judge call.
    @return Reply.
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
    ## RETRIED WITH BACKOFF, because the observed failure is TRANSIENT CAPACITY rather than a
    ## broken call. Measured: three cells came back 85-100% unruled — EVERY call failing, not
    ## some — and the identical call succeeded minutes later with no code change. A judge that
    ## degrades under sustained load gets worse exactly as a grid gets bigger, which is when
    ## unruled marks do the most damage.
    ##
    ## Bounded rather than indefinite: a genuinely broken invocation must still surface as an
    ## error instead of hanging a run. A missing binary is not retried at all, since it will not
    ## fix itself and would burn the whole budget.
    last = Reply(error="no attempt made")
    for attempt in range(ASK_ATTEMPTS):
        if attempt:
            time.sleep(ASK_BACKOFF_SECONDS * attempt)
        try:
            done = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            last = Reply(error=f"timeout after {timeout}s: {exc}")
            continue
        except OSError as exc:
            return Reply(error=f"transport: {exc}")
        if done.returncode != 0:
            last = Reply(
                error=f"rc={done.returncode} after {attempt + 1} attempt(s): "
                f"{done.stderr.strip()[:300]}"
            )
            continue
        try:
            return Reply(text=str(json.loads(done.stdout).get("result") or ""))
        except (json.JSONDecodeError, AttributeError) as exc:
            last = Reply(error=f"unparseable envelope: {exc}")
    return last


## @brief Build the per-mark verdict prompt.
## @param mark_text The frozen mark text.
## @param answer Anonymised answer.
## @return Prompt string.
## @version 1
def verdict_prompt(mark_text: str, answer: str) -> str:
    """QUOTE COMES BEFORE VERDICT, and that order is load-bearing. Asked for the verdict first,
    a judge commits and only then produces evidence, with no retrieval step in between — which
    is how a reply reads `VERDICT: MISS / QUOTE: NONE` against text sitting in the paragraph it
    was grading.

    @brief Verdict prompt.
    @return Prompt.
    @version 1
    """
    width = max(len(v) for v in VERDICTS)
    rules = "\n".join(f"{v:<{width}} — {_RULES[v]}" for v in VERDICTS)
    return f"""You are grading ONE checklist item from a frozen grading key against a candidate
answer about a software codebase. You have NO access to the codebase; judge only whether the
ANSWER demonstrates the item. Do not reward the answer for being good in general — judge THIS
item and nothing else.

CHECKLIST ITEM:
{mark_text}

CANDIDATE ANSWER:
<<<ANSWER
{answer}
ANSWER>>>

Verdicts:
{rules}

SEARCH THE ANSWER FIRST, THEN DECIDE — in that order. Scan the whole answer, including its
tables, bullets, headings and parenthetical asides, for the substance of the item. Write the
quote down BEFORE you settle the verdict. If you find the substance the verdict is HIT and you
must not then talk yourself out of it on grounds of wording, prominence or arrangement.
QUOTE: NONE with VERDICT: HIT is a contradiction; so is quoting the item's substance and then
answering MISS.

Reply with EXACTLY ONE of these blocks, as the LAST thing in your reply:
QUOTE: <short verbatim quote from the answer carrying the item's substance, or NONE>
VERDICT: <one of {", ".join(VERDICTS)}>
WHY: <one line>"""


## @brief Build the set-extraction prompt.
## @param instruction The mark's `extract` text.
## @param answer Anonymised answer.
## @return Prompt string.
## @version 1
def extract_prompt(instruction: str, answer: str) -> str:
    """THE CORRECT SET IS NEVER SHOWN. The judge reports what the answer names; recall and
    precision are then arithmetic over that list. Showing the expected set would turn extraction
    into matching and would make precision meaningless.

    @brief Extraction prompt.
    @return Prompt.
    @version 1
    """
    return f"""Read the candidate answer below and report ONLY what it names. You have no access
to the codebase and you are NOT judging whether the answer is correct or complete — you are
transcribing what it says. Do not add items the answer does not name, and do not omit ones it
does, including any you believe to be wrong.

INSTRUCTION:
{instruction}

CANDIDATE ANSWER:
<<<ANSWER
{answer}
ANSWER>>>

Reply with EXACTLY this block, as the LAST thing in your reply:
ITEMS:
<one item per line, or the single word NONE>
END"""


## @brief Pull the verdict token out of a judge reply.
## @param text Judge reply text.
## @return Token, or None when nothing unambiguous is present.
## @version 1
def read_verdict(text: str) -> str | None:
    """Takes the LAST `VERDICT:` line. A judge that shows a verdict and then revises it has
    revised it; taking the first would score the discarded one.

    @brief Extract a verdict.
    @return Token or None.
    @version 1
    """
    found = re.findall(r"^\s*VERDICT:\s*([A-Z_]+)\s*$", text, re.MULTILINE)
    if not found:
        return None
    token = found[-1].strip().upper()
    return token if token in VERDICTS else None


## @brief Pull the extracted item list out of a judge reply.
## @param text Judge reply text.
## @return Tuple of items, empty when the answer named none.
## @version 1
def read_items(text: str) -> tuple[str, ...] | None:
    """Returns None only when the block is ABSENT — which is a transport-shaped failure, not an
    empty answer. An explicit NONE returns an empty tuple, and the two must not collapse:
    "named nothing" scores 0 recall, "the judge did not reply" scores nothing at all.

    @brief Extract named items.
    @return Items, or None when the block is missing.
    @version 1
    """
    match = re.search(r"^\s*ITEMS:\s*$(.*?)^\s*END\s*$", text, re.MULTILINE | re.DOTALL)
    if not match:
        return None
    body = [line.strip().strip("`-*• ") for line in match.group(1).splitlines()]
    items = [line for line in body if line]
    if len(items) == 1 and items[0].upper() == "NONE":
        return ()
    return tuple(items)


## @brief Majority-voted verdict across n independent samples.
## @param mark_text The mark being judged.
## @param answer Anonymised answer.
## @param model Dated model id.
## @param n Samples to request.
## @return Vote.
## @version 2
def vote(mark_text: str, answer: str, model: str, n: int) -> Vote:
    """AGREEMENT IS OVER SAMPLES REQUESTED, never over survivors. One verdict plus two errors
    under a survivor denominator reads as unanimity, which makes a vote look MORE decisive the
    flakier the judge got.

    @brief Voted verdict.
    @return Vote.
    @version 2
    """
    requested = max(1, n)
    counts: Counter = Counter()
    errors = 0
    ## THE REASON IS KEPT, not just the count. "3/3 calls failed" cannot tell a reader whether
    ## the judge was rate-limited, timed out, or replied without a verdict block — three
    ## failures needing three different responses. Recording only the tally made an unruled
    ## decision uninvestigable after the fact.
    reasons: list[str] = []
    prompt = verdict_prompt(mark_text, answer)
    for _ in range(requested):
        reply = ask(prompt, model)
        token = None if reply.error else read_verdict(reply.text)
        if token is None:
            errors += 1
            reasons.append(reply.error or "reply carried no VERDICT line")
            continue
        counts[token] += 1
    if not counts:
        return Vote(None, 0.0, (), requested, errors, tuple(reasons))
    top, top_n = counts.most_common(1)[0]
    return Vote(
        top, top_n / requested, tuple(sorted(counts.items())), requested, errors, tuple(reasons)
    )
