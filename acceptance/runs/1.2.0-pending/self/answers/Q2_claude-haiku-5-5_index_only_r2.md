An empty search reply is built to tell "looked and found nothing" apart from "this layer never looked," and the two carry different confidence. I ran one probe with a made-up token to see the shape. The reply has these parts:

- **`count: 0`, `results: []`**: the bare empty result.
- **`note`**: states that this is "a definitive empty result from the database, NOT an error," and names what was searched: function, variable, macro, typedef, enum, and class/struct names, macro expansions, the config symbols the repo gates on, and file docs. It also says what was *not* searched: markdown and Kconfig prose, which is `search(corpus='prose')`.
- **`scope`**: the coverage of the index. It gives the file count (426 here), the top-level directories, the extensions indexed, and a `not_indexed` list with counts per extension (here `.rs=2`, `.toml=2`, no-extension=3, `.csv=3`, and others). This is the field that shows whether the place a name lives was covered at all.
- **`target`**: the repository that answered. A mismatch here means you asked the wrong index.
- **`staleness`**: present only when the index is older than the source. Its absence means the answer reflects the current tree.
- **`not_searched`**: appears on split indexes (first-party plus vendored) and names parts that were not read.

For a multi-token search, every token must match within one searchable unit, and the schema says a miss names the token that emptied the result. Searching for a single distinctive word avoids that ambiguity.

**How much confidence each answer deserves**

| Empty reply shows | What it supports |
|---|---|
| `definitive` note, matching `target`, no `staleness`, the name's *kind* is inside the searched set | Strong evidence the repo has no indexed symbol by that name. Not a claim about prose, configs outside the index, or files in `not_indexed`. |
| Same, but the name is conceptual or the repo's docs are the likely home | Weak. Rerun with `corpus='prose'` before concluding anything. |
| The likely home is an extension in `scope.not_indexed` (e.g. `.rs`, `.toml`) | No answer. The file exists but was never read, so the empty result is "not looked." |
| `staleness` present | Refresh first. Files added since the build are invisible. |
| Target is a file outside the indexed set (Makefile, CI config) | No answer. The tool's own instructions say the index cannot settle these. Read the file directly. |

So a clean empty symbol search against the correct, current target is a reasonable basis for "this repository has no such symbol." It does not establish that the repository lacks the concept, the prose mentions it, or the name lives in a file type the index skipped. Those cases need the prose corpus, a `scope` check, or reading the file directly.