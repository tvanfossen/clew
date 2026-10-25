**Short answer:** the reply tells you which places it searched and which it didn't. A "no rows" result is a firm answer only for the places it searched, and the reply says so itself.

I ran a probe with a made-up name, `zzqx_nonexistent_symbol_probe`, to see the shape. It returned `count: 0` and a `note` that calls the result "a definitive empty result from the database, NOT an error and NOT a malformed call," with an instruction not to retry. The reply also carries three things that set the scope:

- **`scope`**: the indexed footprint. Here that is 426 files, whole-repo, extensions `.c .cpp .h .json .md .py .yaml`, with a `not_indexed` list (`.rs`, `.toml`, `.sql`, `.lock`, `.csv`, `.jsonl`, `.motor`, and no-extension files).
- **`note`, "Searched:"**: names and `@brief` text of functions, variables, macros, typedefs, enums and enum values, macro expansions, classes/structs/unions, the config symbols the repo gates on, and file docs.
- **`note`, "NOT searched:"**: markdown and Kconfig prose, which is a separate corpus (`search(corpus='prose')`).
- **`target`**: the repository that answered. Here it is the repo root, so the answer came from the right index.

A `staleness` block appears only when the index is stale. Its absence here means the index is current.

**How much confidence each answer gets**

| Situation | What the reply supports | Confidence |
|---|---|---|
| Zero rows, name-like query, `target` is the right repo, no `staleness`, the kind of thing sits in a searched layer | "This repo does not define that symbol" | High. The reply says not to retry. |
| Zero rows for a conceptual phrase | Only "no symbol's name or brief matches" | Low. Try `corpus='prose'`, since the words may live in docs. |
| Zero rows, and the thing would live in a `not_indexed` extension, a Makefile, CI config, or other non-indexed file | Nothing. The index never looked there. | None. The reply can't settle it. |
| Zero rows for a multi-word query | Every token must match one unit, so one missing token empties the result | Re-query with the most distinctive token before concluding. The multi-token miss names the token that caused it. |
| Symbol has no doxygen brief (`provenance: 'ast'`) | Matching was by name only | An empty brief means unparsed, not undocumented. A concept-level query can miss it. |

**Practical rule:** treat "no rows" as "absent from these layers of this index." Escalate to prose, check the `scope` extensions and `not_indexed` list, and only then conclude the repo lacks the thing. Anything outside the indexed file set needs a direct read of the file, not a retry of the index.

I couldn't check any of this against the source, since I only had the index tools. The reading above comes from the probe reply and the tool descriptions.