# SPDX-License-Identifier: MIT
"""Reproduce ONE judge call exactly as the grader makes it, and show the raw failure.

WHY THIS EXISTS. Seven of twenty graded cells came back majority-unruled with `rc=1`, while a
bare `claude -p` against the same model answered in three seconds. The difference is in the argv
the grader builds, and the only way to find it is to make that exact call and look at what comes
back instead of what the grader records.

@brief Reproduce one judge call verbatim.
@version 1
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from acceptance.grader import judge  # noqa: E402
from acceptance.grader.rubric import load  # noqa: E402


## @brief Make one judge call and print the raw result.
## @return Exit code.
## @version 1
def main() -> int:
    """@brief Probe one judge call.
    @return Exit code.
    @version 1
    """
    answer_path = ROOT / sys.argv[1]
    rubric = load(ROOT / sys.argv[2])
    qid = answer_path.stem.split("_")[0]
    question = next(q for q in rubric.questions if q.id == qid)
    mark = question.marks[1]

    prompt = judge.verdict_prompt(mark.text, judge.anonymise(answer_path.read_text("utf-8")))
    print(f"prompt bytes: {len(prompt)}")
    argv = [
        "claude",
        "-p",
        prompt,
        "--model",
        rubric.judge_model,
        "--output-format",
        "json",
        "--allowedTools",
        "",
    ]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=300, check=False)
    print(f"rc={done.returncode}")
    print(f"stdout[:600]: {done.stdout[:600]!r}")
    print(f"stderr[:600]: {done.stderr[:600]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
