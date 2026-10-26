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

import hashlib
import json
import re
import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

VERDICTS: tuple[str, ...] = ("HIT", "MISS")

## Attempts per judge call and the linear backoff between them — 0s, 60s, 120s, 180s: TEN MINUTES
## of patience in total, then it gives up.
##
## SIZED FOR A CAPACITY REFUSAL, NOT A NETWORK BLIP. The previous 3 x 4s covered twelve seconds,
## and a capacity refusal is measured in minutes — this account hit one naming a reset hours
## away. Measured consequence: seven of twenty graded cells came back majority-unruled, each
## having exhausted every attempt inside the same twelve seconds.
##
## Bounded on purpose. An unbounded retry would hang a ninety-cell grade on one bad cell, and a
## grade that never finishes is worse than one with a named gap in it.
ASK_ATTEMPTS = 4
ASK_BACKOFF_SECONDS = 60
DEFAULT_TIMEOUT = 180

## A FAILURE THAT TOOK NO API TIME NEVER REACHED THE SERVER, so the minute-scale backoff buys
## nothing — it was written for a server saying "slow down". Measured on the first published
## grid: 12.2% of one target's decisions failed with `duration_api_ms: 0`, zero tokens and no
## cost, and each one was slept on for 60 + 120 + 180 seconds. Six minutes per decision,
## eighteen per k=3 mark, and that waiting — not the judging — was most of a 3.9-hour pass.
FAST_BACKOFF_SECONDS = 2

## WHAT "CANNOT RUN RIGHT NOW" LOOKS LIKE. Shared with
## `provision.check_index_tools_reachable`, which needs the broad set: for a probe, every one of
## these means the same thing — the result says nothing about the config, so re-run later.
CAPACITY_PHRASES = (
    "usage limit",
    "session limit",
    "rate limit",
    "quota",
    "overloaded",
)

## THE JUDGE NEEDS A NARROWER SET, AND CONFLATING THE TWO IS A REGRESSION. An account limit is
## not transient: the next call fails identically and the pass writes a hole into every cell it
## touches, so it must stop. A 529 "overloaded" or a rate limit is the OPPOSITE — a server
## saying slow down, which clears in seconds and is precisely what the backoff exists for.
##
## Aborting on those would have been worse than the behaviour it replaced, and the existing
## retry test caught it: its fixture fails three times with "overloaded" and then succeeds,
## which is the measured shape of a transient failure on this transport.
ACCOUNT_LIMIT_PHRASES = (
    "usage limit",
    "session limit",
    "quota",
)


## @brief The grade pass cannot continue because the account is out of capacity.
## @version 1
class JudgeCapacityError(RuntimeError):
    """NOT AN UNRULED DECISION. An unruled decision means the judge could not decide; a usage
    limit means nobody asked it. Recording the second as the first puts holes in a measurement
    and attributes them to the answers, when the remedy is to wait and regrade.

    Raised rather than returned, because every remaining call in the pass will fail the same
    way: continuing spends the rest of the grid's patience discovering that repeatedly. Grading
    is additive and re-runnable, so stopping loses nothing but the wait.

    @brief Out of capacity.
    @version 1
    """


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
    ## WHAT THE JUDGE SAID FOR THE VERDICT THAT WON — its own `QUOTE:` and `WHY:`, which the
    ## harness asked for and then discarded for every binary decision. An audit of 26 failed
    ## decisions found 11 carrying no reason at all and named that as its first obstacle.
    ## Only the winning samples' reasons are kept: a dissenting sample explains a verdict that
    ## was not recorded, and pairing it with the recorded one would mislead.
    rationale: tuple = ()


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
## @brief Whether a failed call's output names an ACCOUNT limit, not a transient one.
## @param text The call's combined stderr and stdout.
## @return True when the account, not the server or the call, is the problem.
## @version 2
def _is_account_limit(text: str) -> bool:
    """NARROW BY DESIGN — see `ACCOUNT_LIMIT_PHRASES`. A server saying "slow down" is retried;
    only an account that has run out stops the pass.

    @brief Account-limit test.
    @return True for a usage, session or quota block.
    @version 2
    """
    low = text.lower()
    return any(phrase in low for phrase in ACCOUNT_LIMIT_PHRASES)


## @brief Whether a failed call reached the server at all.
## @param stdout The call's stdout, which may hold a JSON envelope.
## @return True when the envelope reports zero API time.
## @version 1
def _took_no_api_time(stdout: str) -> bool:
    """UNPARSEABLE MEANS UNKNOWN, AND UNKNOWN KEEPS THE LONG BACKOFF. Guessing "fast" on a
    reply that could not be read would turn a genuine server-side failure into a tight retry
    loop, which is the one behaviour the original backoff exists to prevent.

    @brief Zero-API-time test.
    @return True only when the envelope says so.
    @version 1
    """
    try:
        return int(json.loads(stdout).get("duration_api_ms", -1)) == 0
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        return False


## WHERE VERDICTS ARE REMEMBERED, or None to judge afresh every call.
##
## WHY A CACHE AND NOT temperature=0. The judge reaches the model through the `claude` CLI, which
## exposes no temperature, seed or top_p flag — so every call is a sample at default sampling and
## re-grading the same answer produces a DIFFERENT score. Measured on 21 re-graded cells: 8.95 pt
## mean absolute spread, larger than most effects this harness exists to detect.
##
## The alternative — calling the API directly to pin temperature — moves ~3.1M judge input tokens
## per pass from a subscription onto metered billing, recurring forever, and still leaves residual
## nondeterminism. A content-addressed cache is strictly better at the thing that was wanted: the
## same answer and the same mark return the SAME verdict BY CONSTRUCTION, and a re-grade costs
## nothing instead of 3,348 calls.
##
## IT MAKES A GRADE REPRODUCIBLE, NOT CORRECT. A wrong verdict becomes reliably wrong, which for a
## published measurement is the better failure: stable, inspectable and challengeable rather than
## different every time anyone checks.
##
## MODULE-LEVEL RATHER THAN THREADED THROUGH, deliberately. The alternative is four layers of
## plumbing — `cmd_grade` to `score_question` to `vote` to `ask` — carrying a parameter every
## layer in between ignores. It is configured once per process by the command that owns the run.
_CACHE_DIR: Path | None = None


## @brief Point the judge cache at a directory, or disable it.
## @param path Directory to store verdicts in, or None to judge afresh.
## @return None.
## @version 1
def configure_cache(path: Path | None) -> None:
    """DISABLING IS HOW THE FLOOR GETS MEASURED. A deliberate second pass with no cache is what
    quantifies judge variance; with the cache on, a second pass would replay the first and report
    a floor of zero — a measurement of the cache rather than of the judge.

    @brief Configure the verdict cache.
    @return None.
    @version 1
    """
    global _CACHE_DIR
    _CACHE_DIR = path
    if path is not None:
        path.mkdir(parents=True, exist_ok=True)


## @brief The cache file for one prompt and model, or None when caching is off.
## @param prompt The exact prompt sent to the judge.
## @param model The judge model id.
## @return Path to the entry, or None.
## @version 1
## @dg_internal
def _cache_entry(prompt: str, model: str) -> Path | None:
    """CONTENT-ADDRESSED ON THE WHOLE PROMPT, which already contains the mark text and the
    anonymised answer, so the key needs nothing else to be exact. The model id is included
    because two models are two instruments.

    @brief Cache path for a call.
    @return The path or None.
    @version 1
    """
    if _CACHE_DIR is None:
        return None
    digest = hashlib.sha256(f"{model}\x00{prompt}".encode()).hexdigest()
    return _CACHE_DIR / f"{digest}.json"


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
    @version 3
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
    entry = _cache_entry(prompt, model)
    if entry is not None and entry.is_file():
        try:
            ## A CACHED ERROR IS NEVER REPLAYED. Only verdicts are stored, so a transient capacity
            ## failure cannot become permanent — it retries on the next pass, as it should.
            return Reply(text=str(json.loads(entry.read_text("utf-8"))["text"]))
        except (OSError, ValueError, KeyError):
            pass

    last = Reply(error="no attempt made")
    fast = False
    for attempt in range(ASK_ATTEMPTS):
        if attempt:
            time.sleep((FAST_BACKOFF_SECONDS if fast else ASK_BACKOFF_SECONDS) * attempt)
        try:
            ## STDIN EXPLICITLY CLOSED. The CLI warns "no stdin data received in 3s,
            ## proceeding without it" when it inherits an idle stdin, and the same call
            ## measured 8.9s with stdin inherited against 3.4s from /dev/null. A COST fix,
            ## not a correctness one — stdin was tested as a suspect for the rc=1 failures
            ## and cleared, both forms succeed. But this grid makes ~2,244 judge calls, so a
            ## few seconds each is hours of a grade spent waiting for input that never comes.
            done = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            last = Reply(error=f"timeout after {timeout}s: {exc}")
            continue
        except OSError as exc:
            return Reply(error=f"transport: {exc}")
        if done.returncode != 0:
            ## STDOUT TOO, NOT JUST STDERR. Measured on the weekend grid: seven cells recorded
            ## "rc=1 after 3 attempt(s):" with NOTHING after the colon, because the CLI puts its
            ## explanation on stdout and only the empty stderr was kept. A recorded reason that
            ## says only "it failed" is the tally this field replaced.
            whole = f"{done.stderr}\n{done.stdout}"
            if _is_account_limit(whole):
                raise JudgeCapacityError(
                    f"the judge is out of capacity, so this pass would record holes rather "
                    f"than verdicts:\n{whole.strip()[:300]}\n"
                    f"Nothing is wrong with the rubric or the answers. Wait for capacity and "
                    f"re-run `grade` — grading is additive, so the passes already written stand "
                    f"and the rest fill in."
                )
            ## A ZERO-DURATION FAILURE NEVER REACHED THE SERVER, so the next attempt comes
            ## quickly; a call that took real time and failed is worth the long wait.
            fast = _took_no_api_time(done.stdout)
            detail = (done.stderr.strip() or done.stdout.strip())[:300]
            last = Reply(error=f"rc={done.returncode} after {attempt + 1} attempt(s): {detail}")
            continue
        try:
            reply = Reply(text=str(json.loads(done.stdout).get("result") or ""))
            if entry is not None:
                ## WRITTEN ONLY ON SUCCESS, and tolerantly: a cache that cannot be written must
                ## not fail a grading pass that otherwise worked.
                try:
                    entry.write_text(
                        json.dumps({"model": model, "text": reply.text}, indent=2), "utf-8"
                    )
                except OSError:
                    pass
            return reply
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


## @brief Pull the judge's stated reason out of a reply.
## @param text Judge reply text.
## @return "QUOTE … | WHY …" as the judge wrote them, or "" when neither is present.
## @version 1
def read_reason(text: str) -> str:
    """**THE JUDGE WAS ASKED FOR ITS REASONING AND THE HARNESS THREW IT AWAY.** The verdict prompt
    requires a `QUOTE:` carrying the item's substance and a one-line `WHY:`, written before the
    verdict is settled — and only `read_verdict` was ever called, so every binary decision landed
    in the record with `detail: ""`.

    Measured cost: an audit of 26 failed decisions found 11 with no stated reason at all, could
    not quote the judge where it disagreed with it, and said so as its first limitation. A
    measurement whose individual decisions cannot be disputed is not inspectable, and this project
    publishes its grids for other people to argue with.

    TAKES THE LAST OF EACH, matching `read_verdict`: a judge that revises its quote has revised
    it, and the reason must describe the verdict actually recorded.

    RETURNS "" RATHER THAN A PLACEHOLDER when the judge wrote neither. A reason that was never
    given and a reason that was lost must not read alike, and "" is what the field already means
    everywhere else in `Decision`.

    @brief Extract the judge's stated reason.
    @return The reason, or "".
    @version 1
    """
    quotes = re.findall(r"^\s*QUOTE:\s*(.+?)\s*$", text, re.MULTILINE)
    whys = re.findall(r"^\s*WHY:\s*(.+?)\s*$", text, re.MULTILINE)
    parts = []
    if quotes:
        parts.append(f"QUOTE: {quotes[-1].strip()}")
    if whys:
        parts.append(f"WHY: {whys[-1].strip()}")
    return " | ".join(parts)


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
    said: dict[str, list[str]] = {}
    prompt = verdict_prompt(mark_text, answer)
    for _ in range(requested):
        reply = ask(prompt, model)
        token = None if reply.error else read_verdict(reply.text)
        if token is None:
            errors += 1
            reasons.append(reply.error or "reply carried no VERDICT line")
            continue
        counts[token] += 1
        ## KEYED BY THE TOKEN IT JUSTIFIED, so the winning verdict's reasons can be selected
        ## after the vote rather than guessed at.
        stated = read_reason(reply.text)
        if stated:
            said.setdefault(token, []).append(stated)
    if not counts:
        return Vote(None, 0.0, (), requested, errors, tuple(reasons))
    top, top_n = counts.most_common(1)[0]
    return Vote(
        top,
        top_n / requested,
        tuple(sorted(counts.items())),
        requested,
        errors,
        tuple(reasons),
        tuple(said.get(top, ())),
    )
