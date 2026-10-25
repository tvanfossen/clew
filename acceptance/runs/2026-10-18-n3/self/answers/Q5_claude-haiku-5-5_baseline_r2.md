Clew has five ways to change how it indexes a repo, and they are not all equal. The rule for conflicts is in `clew/tiers.py`: a stated value (a CLI flag or the `options` argument over MCP) beats the `.clew.yaml` declaration, and the declaration beats clew's built-in guesses. Target-supplied facts are never removed by anything stated.

**The ways to say so**

| Layer | Where it comes from | Effect |
|---|---|---|
| Built-in heuristics (tier 5) | clew's name-pattern defaults | Floor. Any stated value replaces it. |
| Ecosystem (tier 4) | Known-ecosystem signatures, e.g. UDM, ingot | Accumulates. Survives every stated tier. |
| Target facts (tier 3) | Things the repo already wrote: Doxyfile ALIASES/PREDEFINED, generator manifests, language/platform entry points | Accumulates. Survives every stated tier. |
| Declared (tier 2) | `<repo>/.clew.yaml`, discovered from the repo root | Replaces the heuristics. Replaced by a flag. |
| Stated (tier 1) | CLI flags (`--scope`, `--extra-input`, `--shared-key-patterns`, `--doxyfile`, …), or the `options` argument for embedding callers and MCP | Replaces the declaration. |

Inside `.clew.yaml`, `index_scope:` sets the file scope (`clew/scope.py:397-402`), `sub_indexes:` trims vendored trees (`clew/declaration.py:77-81`), and the other sections mirror the standalone manifests (`shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `locks`, `dispatch`, `event_tags`, `preprocessor`, `kconfig`, and so on; `clew/declaration.py:238-258`). The `guard:` section belongs to the gate, not the index. Keys starting with `x-` are tolerated with a warning rather than refused (`clew/declaration.py:274`).

**What happens when two disagree**

- **Flag vs declaration, list-valued option:** the flag wins. The declared list is dropped, but facts and ecosystem entries still apply (`clew/tiers.py:300-335`, `clew/cli.py:1619-1642`).
- **Flag vs declaration, manifest document:** the flag replaces the whole document. There is no merge.
- **Empty value** (`[]` or `{}`) is a withdrawal. It falls through to the declaration, then to the heuristics.
- **Stated `index_scope` with `--scope` other than `from-guard`:** refused with exit 1 (`clew/cli.py:779-799`). Clew does not guess which one you meant.
- **Declared `index_scope` that is unusable** (a root outside the repo, or a malformed block): logged as a warning, and the scope falls back to the whole repository (`clew/scope.py:668-675`).
- **Declared `index_scope` with `--scope doxyfile`:** the declaration is not read on that path, and the refusal only checks the stated one. So the declared scope is silently ignored. I read this from the code and did not run it.
- **`--extra-input`:** appends rather than replaces. It is refused if the Doxyfile's FILE_PATTERNS would exclude every file under it (`clew/cli.py:688-728`).

**One thing to know:** a stated value is recorded in `build_meta` and replayed on later builds of that database. A one-off flag therefore stays in effect for that index until it is withdrawn. Two operators on the same commit can end up with different indexes, but only where the stated value is recorded (`clew/tiers.py:426-465`).

I read the code paths directly and did not run clew or its tests. I did not check the user-facing docs for drift against this behavior.