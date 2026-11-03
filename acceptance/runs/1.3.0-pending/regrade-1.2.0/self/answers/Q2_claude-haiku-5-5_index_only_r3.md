The reply separates the two cases by what it says it searched, not by a single "not found" flag. Each empty result carries three things:

- **A scope block.** It names the target, the file count (426 here), the extensions indexed, and `not_indexed` for extensions the index never reads (here `.rs`, `.toml`, `.csv`, `.sql`, extensionless files and so on).
- **A "NOT searched" line.** It lists the corpora the query did not touch. For `symbols`, that is markdown and Kconfig prose, which `search(corpus='prose')` covers.
- **Per-token hits, plus a staleness marker.** A multi-token miss names the token that emptied the conjunction. `staleness` appears only when the index is stale. Here it is absent, and `index(action='targets')` reports `stale: false` with 0 changed source files.

The reply is explicit that an empty result is "NOT an error" and "NOT a definitive negative either". It tells you to retry with fewer tokens, because a conjunction of two words can fail on one of them alone.

Confidence, roughly:

| Case | What an empty result supports |
|---|---|
| Symbol corpus, index current, one distinctive token retried, file in the 426 indexed files | Strong evidence the repo has no function, variable, macro, type or config symbol with that name. Not proof: a name that only appears in a comment or body text is not in the symbol corpus. |
| Same query against markdown or Kconfig prose | Not covered by the symbol search. Run `corpus='prose'` before concluding anything about docs. |
| Name that would live in a file with an unindexed extension (`.rs`, `.toml`, `.sql`, …) | No evidence either way. The index never read those files, so this is the "did not look there" case. Read or grep those files directly. |
| Index stale (a `staleness` block present) | Treat as unreliable until `index(action='refresh')` runs. Not the case in this session. |

So "the repository does not contain that" is only supported for symbols in the indexed extensions, from a current index, after a retry. "I did not look there" is what the reply says for everything else. Its word for the distinction is the scope and "NOT searched" fields, not an `absent` flag. I checked this with a nonsense query on the live index, so the field names and the behaviour above are observed, not recalled. I did not test a real symbol that happens to live in an unindexed file type, so the claim about those rests on the scope field's contents.