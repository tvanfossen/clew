The reply separates the two cases by saying what it searched, not by a bare "not found." My test query, `zzqx_nonexistent_symbol`, returned `count: 0` with a `note` that lists the layers covered and the layers skipped. The `scope` block then gives the file count, the extensions covered, and a `not_indexed` list. The `target` field names the repository that answered.

**What tells you "not in the repo" from "not looked there"**

| Field | Says | Where the gap shows |
|---|---|---|
| `note` | Which layers were searched (names, `@brief`, macros, typedefs, enums, classes, config symbols, file docs) and which were not (markdown/Kconfig prose, function bodies) | Names the corpus to try next: `prose` or `code` |
| `scope` | 426 indexed files, whole-repo, extensions `.c .cpp .h .json .md .py .yaml` | `not_indexed`: `.rs`, `.toml`, `.sql`, `.csv`, `.jsonl`, `.lock`, `.motor`, and extensionless files, 14 in total |
| `target` | The repository that answered | Wrong target means you searched the wrong repo |
| `not_searched` / `sub_index` | Parts of a split repo that were not read | Absent here, because this repo is not split |
| `index(status)` | `stale`, build version, coverage counts | Stale data would make an empty result unreliable |

The AGENTS.md rule behind this is "absence is not emptiness." An empty list means the layer ran and found nothing. A missing key means the layer never ran, so clew drops `not_indexed` when it is empty instead of emitting `[]`.

**Confidence each answer deserves**

- **"No such defined symbol in the indexed files."** High. The lookup covered names, briefs, macros, types, config symbols and file docs across 426 files, and the reply says not to retry.
- **"The repo does not contain that."** Low to moderate. The lookup did not read function bodies, markdown or Kconfig prose, or any file whose extension is in `not_indexed`. A Rust, TOML or SQL identifier could be present and invisible to `corpus='symbols'`. The `definitive` wording in the reply is accurate only for the layers it names.

**What I'd do next**

Run the same term with `corpus='prose'` and `corpus='code'`. If the name looks like a file, check the `files` layer and the `scope.not_indexed` list before concluding anything.

One thing I did not resolve: `search` reports 426 indexed files, while `index(status)` reports 435 files in scope, 397 indexed, and 15 barren. These may be different measures, but the index does not say so, and I can't tell from here which figure governs the empty-result claim.