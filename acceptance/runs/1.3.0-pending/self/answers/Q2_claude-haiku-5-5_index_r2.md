A zero-row reply doesn't just say "nothing matched." The reply carries enough structure to tell the two cases apart, but it's up to you to read it. I ran two searches on a made-up term to see the shape. The symbol search returned `count: 0` with a `note` that says it is "NOT an error and NOT a malformed call, and it is NOT a definitive negative either." It also included `token_hits` (`zzqxnonexistentsymbol=0`, `frobnicate=0`), a `scope` block, and the `target` that answered.

**The signals, and what each one settles**

| Field | What it tells you | Settles "not in repo"? |
|---|---|---|
| `token_hits` | Which token emptied the conjunction. Every token must appear in one searchable unit. | No. It says the term is missing from the searched units, not from the repo. |
| `scope` (`file_count`, `extensions`, `not_indexed`) | Exactly which files were read. Here: 426 files, with `.rs`, `.toml`, `.sql`, `.lock`, `.csv`, `.jsonl`, `.motor` and extensionless files left out. | Only inside the indexed extensions. Anything in `not_indexed` is "never looked." |
| `note` "NOT searched" list | Markdown and Kconfig prose sit outside symbol search and need `corpus='prose'`. | No. A symbol miss says nothing about prose. |
| `target` | Which repository answered. | Confirms you queried the repo you meant. |
| `staleness` | Present only if the index is older than the source. | A stale index can miss recent additions. |
| `not_searched` (dossier) | Sub-indexes of a split repo that were not read. | Only when present. |

The config corpus reports its own state. In my run `gate_state: "populated"` with 5 gate symbols means the layer was read, so its empty result is a real measurement. `kconfig_found: false` is reported explicitly rather than hidden, so you can see that no Kconfig was located.

**How much confidence each answer deserves**

- **Zero rows, every token missing, all searched extensions in scope, `staleness` absent:** reasonable confidence that no symbol name or `@brief` in the indexed code contains the term. This is not confidence that the term is absent from the repo. Symbol search matches names and briefs, not function bodies, so a term that appears only inside code will still come back empty.
- **Term lives in an extension listed under `not_indexed`:** no confidence. The reply names those files, so use Grep on them.
- **Term is conceptual or lives in docs or Kconfig:** no confidence from the symbol corpus. Retry with `corpus='prose'`.
- **Any `staleness` block or any `not_searched` entry:** treat the negative as provisional until you refresh or query the missing part.
- **A multi-token miss:** this only shows the conjunction failed. Drop the token that matched nothing and retry before concluding anything. The reply itself says so.

The practical rule is the one in the repository's own guidance: check `target` and `not_searched`, and fall back to Grep for any extension the index does not hold, before saying a thing does not exist. I did not run a Grep over the repo to confirm the made-up term is absent. That check would be the ground truth for the un-indexed extensions.