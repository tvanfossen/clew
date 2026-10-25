The reply separates the two cases through its fields, not through a yes/no flag. An empty search returns `count: 0` and `results: []`, and the `note` says outright that this is "NOT an error and NOT a definitive negative." Several other fields carry the rest of the answer:

| Field | What it tells you |
|---|---|
| `token_hits` | Per-token counts. A multi-token query is a conjunction, so a zero for one token explains the empty result. |
| `scope` | What was indexed: 426 files, whole-repo, the extensions covered, and `not_indexed` (e.g. `.rs=2`, `.toml=2`, `.sql=1`, no-extension files). |
| `target` | The repository the query answered from. Check this before concluding anything. |
| `staleness` | Present only if the index is stale. Absent here, so the index is current. |
| `note` | Lists what was searched (names, `@brief`, macros, typedefs, enums, classes, config symbols, file docs) and what was not (markdown and Kconfig prose, which is `corpus='prose'`). |

For the `files` corpus the reply is blunter: it says this corpus holds indexed source files only, so build scripts, Doxyfiles and data files are absent "by construction." It points to `doc_scope` and `inventory` and suggests a broader glob.

**Confidence each answer deserves**

- **"Not a symbol in the indexed source."** Fairly strong, if all of these hold: `target` is the repo you meant, there is no `staleness` block, the query is a single distinctive token (the tool itself says to retry without the non-matching tokens), and the name is the kind of thing the symbol corpus covers. It is still a claim about the index's coverage, not about the tree.
- **"Not in the repository."** Not established by an empty search alone. The name could live in:
  - prose or Kconfig (search `corpus='prose'`)
  - an extension the index does not parse (`.rs`, `.toml`, `.sql`, Makefiles, CI configs)
  - a vendored tree held in a separate `sub_index`
  - a spelling that differs for different consumers

  Closing that gap takes a prose search and a shell grep over the full tree.
- **Empty `files` corpus.** Weakest evidence. It says nothing about whether a file exists on disk, only that the index does not hold it as a parsed source file.

I ran two probes: a nonsense two-token symbol query and a nonsense file query. Both came back empty with the notes above. I did not run the prose search or a shell grep, so the claim that the name is absent from the repository is unverified.