**Short answer:** the reply tells you which place it searched and how many tokens it matched. Whether an empty result is a real absence depends on which corpus you queried, so the confidence has to be read per reply.

**What distinguishes the two cases in the reply**

- **Symbol search (the default corpus).** The reply says the empty result is "NOT a definitive negative." It lists what it searched: names, `@brief` text, macros, typedefs, enums, classes/structs, config symbols, and file docs. It also lists what it did not search: markdown and Kconfig prose. It gives `token_hits` per word, so a zero on one token is visible. It also gives a `scope` block: 426 indexed files, the extensions covered, and a `not_indexed` list (14 entries, including `.rs`, `.toml`, `.csv`, `.sql`, `.lock`, and extensionless files). The `target` field names the repository that answered.
- **Prose search (`corpus='prose'`).** The reply says "This IS a definitive empty result from the database" and tells you not to retry. It does not repeat the `scope` block, so the bounds of that claim come only from the `target` field and the repository's own index.

**What each answer is entitled to**

| Reply | Entitled to | Not entitled to |
|---|---|---|
| Symbol search, all tokens zero | The name is not a symbol, brief, macro, type, or config symbol in the 426 indexed files of `target`. Strong evidence. | That the name is absent from the repo. It may sit in an unindexed extension, in a markdown or Kconfig file, or be spelled differently. |
| Symbol search, one token zero | The zero token is the cause. The reply's own guidance is to retry without it. | Anything about the other token alone, since matching is a conjunction. |
| Prose search, zero | Absent from the indexed markdown for `target`. Stated as definitive. | Absence from non-markdown text or unindexed files. |

**Where the search did not look**

- Files outside the 426 indexed files, and extensions in `not_indexed`.
- Markdown and Kconfig prose, if you queried symbols.
- Build and CI files such as Makefiles and CI configs, which the clew instructions say sit outside the indexed set.
- A different repository, if `target` is not the one you meant.

**What I checked:** two probe searches with a nonsense token. The symbol search returned zero with the "not definitive" note, per-token zeros, and the scope block. The prose search returned zero with the "definitive" note. I did not run `dossier` or `index`, so the claims about `not_searched` on split indexes and about how absent keys are handled come from the tool descriptions and the repo's AGENTS.md, not from a reply I observed.