# Superseded — the two-arm instrument

These 30 cells were generated on 2026-10-18 by the TWO-ARM instrument (`baseline` vs
`index_only`) whose `index_only` brief ended *"say so plainly rather than guessing — an honest
gap is the useful answer here"*, a clause the baseline brief never carried.

They are NOT part of the three-arm grid and must not be graded with it. Moved aside rather than
deleted for two reasons: they are the only record of what that instrument measured
(index_only -11.4pt on mbedtls, which is what motivated every change that followed), and
`--resume` skips any cell whose `.md` already exists, so leaving them in `answers/` would have
silently mixed two instruments inside one published run.

Their grades carry `rubric_digest` for mbedtls 3.1.0 and a `grader_fingerprint` from before the
judge retry change, so nothing downstream can mistake them for current.
