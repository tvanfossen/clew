# Q6 — mcp — sonnet — run 1

Enough evidence. Composing the final answer.

## Answer

The program's YAML manifests are read through a small number of distinct schema layers, and each layer independently decides what happens to a mistyped key. There is no single validator for the whole file — a typo's fate depends on *which* level it's in.

### Level 1 — the document's top-level section names

`load_declaration_located()` reads `.doxyguard-db.yaml` (or the `x-` passthrough in `.doxygen-guard.yaml`) and checks every top-level key against `KNOWN_SECTIONS` — a frozenset of the exact accepted spellings, e.g. `shared_key_patterns` (plural), `thread_patterns`, `dispatch`, `locks`, `requirements`, etc. (`doxyguard_db/declaration.py:234-251`, list assembled from `SECTION_*` constants at `doxyguard_db/declaration.py:85-214`).

If your colleague writes `shared_key_pattern` (singular) instead of `shared_key_patterns`, `load_declaration_located` raises `DeclarationError`, naming the bad key and the full allowed set (`doxyguard_db/declaration.py:327-335`):
```
raise DeclarationError(
    f"{path}: unknown section(s) {...} — allowed: {...}. Nothing reads an "
    f"unknown section, so the build would have used built-in defaults "
    f"while reporting that your declaration was honoured."
)
```
This is a deliberate, documented choice (`doxyguard_db/declaration.py:281-300`): unlike a broken file, a misspelled section still parses as valid YAML, and the author clearly intended something — silently falling back to defaults there would look like success. **The build refuses outright.**

### Level 2 — entries inside a section, and here it forks in two directions

**a) `dispatch:` section entries — same fail-closed treatment, one level down.**
`_interface_entry`, `_table_entry`, and `_wrapper_entry` each call `_reject_unknown(entry, <ALLOWED_KEYS>, owner)` (`doxyguard_db/dispatch.py:327,354,375`), and the top-level document keys of the `dispatch:` block itself are checked the same way at `doxyguard_db/dispatch.py:429`. `_reject_unknown` (`doxyguard_db/dispatch.py:109-123`) raises `DeclarationError` naming the bad key(s) and the allowed set, exactly mirroring the section-level check. A typo'd key inside a `dispatch:` interface/table/wrapper entry is refused.

**b) `shared_key_patterns:` entries — no rejection at all; the typo is silently absorbed.**
`_parse_pattern_entry` (`doxyguard_db/shared_key_edges.py:533-556`) validates only `dispatch_mode` against a vocabulary (raising if that specific field is wrong). But the key fields themselves are read with `.get(..., default)`:
```python
return AccessorPattern(entry["pattern"], int(entry.get("key_arg_index", 0)), dispatch_mode)
```
There is no `_reject_unknown` here. So if your colleague mistypes `key_arg_index` as `key_arg_idx`, `entry.get("key_arg_index", 0)` finds nothing, silently defaults to `0`, and the manifest is accepted — but every accessor gets keyed off argument 0 regardless of what was actually intended. **No error, no warning — a quietly wrong dataflow graph.** This exact trap is called out in the repo's own CLAUDE.md as a known danger.

### A correctly written manifest

Passes through both checks with nothing raised: `load_declaration_located` logs `declaration: <path> declares <section names>` at INFO (`doxyguard_db/declaration.py:336`) and the parsed mapping is used to override built-in defaults.

### A file that isn't valid YAML at all

This is handled by an *earlier*, separate layer: `_read_mapping` (`doxyguard_db/declaration.py:345-357`). A `yaml.YAMLError` (bad syntax) or an `OSError` (unreadable file), or a file that parses but isn't a mapping (e.g. a bare list), is caught, logged at **WARNING**, and treated as `{}` — i.e., the declaration is silently ignored and the build proceeds entirely on built-in defaults. This is the opposite of the section/key-typo case: unparseable YAML is "an accident with nothing recoverable in it," so it degrades gracefully rather than failing the build; a misspelled-but-parseable key is "a document that parses, where the author plainly intended something," so — at the section level and in `dispatch:` entries — it refuses instead.

## Gaps

- I did not exhaustively check every other section's entry-level parser (`entry_patterns`, `thread_patterns`, `locks`, `event_tags`, etc.) for whether they follow the `_reject_unknown` pattern or the silent-default pattern like `shared_key_patterns` — I verified the two contrasting cases (`dispatch` vs `shared_key_patterns`) via the index and a direct read of `shared_key_edges.py`, but did not check the remaining ~8 sections' entry parsers individually.
- The `mcp_server` and `buildoptions.py` "Tier 1" structured-options path (mentioned in search results) is a separate, non-YAML input tier I did not trace further since the question is specifically about YAML manifests.
