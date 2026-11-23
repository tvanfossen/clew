**Short answer:** an empty reply does not mean "absent." It means "absent from the places the tool looked," and the reply tells you which places those were. Confidence depends on how far that set reaches.

I ran a probe for a made-up name (`zzqx_nonexistent_symbol_probe`) against this repo. The reply had these parts:

- **`count: 0`, `results: []`**: the empty result itself.
- **`note`**: says this is a definitive empty result, not an error or malformed call, and tells you not to retry. It also lists what was searched (names, `@brief`s, macros, typedefs, enums, classes, config symbols, file docs) and what was not (markdown or Kconfig prose, and function bodies).
- **`scope`**: the coverage. Here it is whole-repo, 426 files, with extensions `.c .cpp .h .json .md .py .yaml`. It also lists `not_indexed` by extension (`no extension=3`, `.csv=3`, `.rs=2`, `.toml=2`, `.jsonl=1`, `.lock=1`, `.motor=1`, `.sql=1`), so those files were never read.
- **`target`**: the repo that answered. This is what tells you the query ran against the right repository.

**How to tell the two cases apart**

| Signal | Means |
|---|---|
| `target` matches the repo you meant | The right index answered |
| `scope.not_indexed` lists the file type you care about | "Not looked" in that file type. Zero is not evidence |
| `note` "NOT searched" names your corpus (prose, code bodies) | Run `search(corpus='prose')` or `corpus='code'` before concluding |
| `not_searched` (split repos) | A vendored or first-party part was never read |
| `staleness` present | Index is behind the source; recent additions may be missing |
| `exclude` in `.clew.yaml` | Deliberately left out, so zero is a choice, not a finding |

Note the design rule: the codebase's contract is that absence of a key means "nothing was missed," and an empty list is a claim that it looked. So a present `not_indexed` key is the thing to read, not the zero count.

**Confidence each answer deserves**

- **"No symbol with this name" in the searched set:** high. Here the tool says it is definitive, and the probe bears that out: a repeat query would return the same zero. It is still only as good as the corpus named in the note.
- **"The string appears nowhere in the repo":** low. Symbol search does not cover function bodies, markdown or Kconfig prose, or the `not_indexed` file types. Use `search(corpus='code')` for literals and keys, `corpus='prose'` for concepts, and read the source for things the index does not cover (Makefile, CI config, `.rs` or `.sql` files here).
- **"This repo does not contain X" when `not_indexed` includes X's file type:** no confidence. The zero is a scope fact, not a finding about the code.