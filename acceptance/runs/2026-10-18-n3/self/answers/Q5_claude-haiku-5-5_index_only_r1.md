There are three ways to tell clew how to index a repository, ordered from strongest to weakest:

| Tier | Source | Who uses it |
|---|---|---|
| 1 | Explicit value stated at call time: a CLI flag, or the structured `options` argument for embedding callers | An operator, one-off |
| 2 | The repo's checked-in `.clew.yaml` declaration | The repo owner, standing config |
| 5 | Built-in guesses, such as name-shape heuristics and default entry patterns | clew itself |

Tiers 3 and 4 are different in kind. Tier 3 is language and platform entry points, and they accumulate underneath whatever is stated. Tier 4 is a generated data model's own manifest. I didn't get the full tier table verbatim from the index, so treat those two as a summary.

The `.clew.yaml` route is the one that works everywhere. The MCP server passes no CLI flags, so a declaration is the only way a repo can configure it through MCP. The old `.doxygen-guard.yaml` is no longer read, and a repo that hasn't moved its config gets the defaults.

**When they disagree**

- **Stated beats guessed.** A declaration or flag displaces tier-5 guesses. Entry patterns are the example: a declared pattern replaces the guesses instead of extending them.
- **Flag beats file.** For one option, a CLI flag wins over `.clew.yaml`. The file is the standing statement and the flag is a deliberate one-off override.
- **Declaration beats convention.** A declared catalog path (`impact.requirements.file`) wins over a conventional `requirements.yaml`. Convention applies only when nothing is declared. The tests show the CLI and MCP entry points once disagreed on this, and they now share one rule.
- **Declared patterns beat defaults.** A declared shared-key pattern takes precedence over a built-in default with a colliding prefix. Matching is first-match, so declared patterns must be checked before the defaults.
- **Lists differ by option.** Some options replace the default list and others extend it. `key_alias_prefixes` replaces, and tier 3 accumulates.
- **Resolution is recorded.** The tier that won is written into build metadata. The stated value is recorded only when tier 1 won, so a replayed build doesn't mistake a declaration or a guess for something an operator typed.

**Failure cases, which are not disagreements**

- An unknown section name in `.clew.yaml` is refused by name and the build stops. The error lists the allowed sections.
- A malformed declaration is ignored with a message, and built-in defaults apply. The message says the file was ignored, so the owner can see it.
- A comments-only file is reported as stating nothing.

I did not verify the scope-specific order from the index directly. The docs say a declaration beats the `guard:` section, which beats the Doxyfile, but the scope rule is only in a test name and a doc sentence.